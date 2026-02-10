from flask import Flask, jsonify, request
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
# Permitir CORS para que el frontend pueda comunicarse con el backend
CORS(app)

# Configuración de conexión a Neon
DB_URL = "postgresql://neondb_owner:npg_XvuILHgEf72P@ep-jolly-surf-aitj3dp7-pooler.c-4.us-east-1.aws.neon.tech/neondb?sslmode=require"

def get_db_connection():
    return psycopg2.connect(DB_URL)

# --- 1. DASHBOARD ---
@app.route('/api/dashboard-data', methods=['GET'])
def get_dashboard_data():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Obtener tickets con nombres de empresa y técnico
        cur.execute("""
            SELECT t.codigo, t.fecha_creacion as fecha, e.empresa, t.estado, 
                   (tec.nombre || ' ' || tec.primer_apellido) as tecnico_nombre
            FROM tickets t 
            LEFT JOIN cliente c ON t.id_clientes = c.id
            LEFT JOIN empresas e ON c.id_empresa = e.id
            LEFT JOIN fichas_tecnicas f ON t.id = f.id_ticket
            LEFT JOIN tecnicos tec ON f.id_tecnico = tec.id
            ORDER BY t.fecha_creacion DESC;
        """)
        tickets = cur.fetchall()

        # KPIs Generales
        cur.execute("""
            SELECT 
                (SELECT COUNT(*) FROM tickets) as total,
                (SELECT COUNT(*) FROM tickets WHERE estado = 'ABIERTO') as abiertas,
                (SELECT COUNT(*) FROM tickets WHERE estado = 'EN ATENCIÓN') as atencion,
                (SELECT COUNT(*) FROM tickets WHERE estado = 'ESPERA_REFACCION') as espera,
                (SELECT COUNT(*) FROM tickets WHERE estado = 'RESUELTO') as resueltos,
                (SELECT COUNT(*) FROM tecnicos) as total_tecnicos,
                (SELECT COUNT(*) FROM cliente) as total_clientes,
                (SELECT COUNT(*) FROM empresas) as total_empresas
        """)
        stats = cur.fetchone()
        
        return jsonify({"status": "success", "tickets": tickets, "stats": stats})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn: conn.close()

# --- 2. TÉCNICOS ---
# --- ENDPOINT: CLIENTES ---
@app.route('/api/tecnicos-detallados', methods=['GET'])
def get_tecnicos_detallados():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # UNIÓN DE TABLAS: tecnicos + especialidad 
        query = """
            SELECT 
                t.id, t.id_telegram, t.nombre, t.primer_apellido, 
                e.especialidad as nombre_especialidad, t.activo
            FROM tecnicos t
            LEFT JOIN especialidad e ON t.id_especialidad = e.id
            ORDER BY t.nombre ASC;
        """
        cur.execute(query)
        tecnicos = cur.fetchall()
        cur.close()
        return jsonify(tecnicos)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn: conn.close()

# Endpoints adicionales para Clientes y Fichas (restaurados)
@app.route('/api/clientes-detallados', methods=['GET'])
def get_clientes_detallados():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT c.*, e.empresa as nombre_empresa FROM cliente c LEFT JOIN empresas e ON c.id_empresa = e.id;")
        clientes = cur.fetchall()
        cur.close()
        return jsonify(clientes)
    except Exception as e: return jsonify([]), 500
    finally:
        if conn: conn.close()
# --- 4. CATÁLOGOS ---
@app.route('/api/catalogos/<tabla>', methods=['GET'])
def obtener_catalogo(tabla):
    config = {
        'empresas': {'col': 'empresa', 'id': 'id'},
        'equipo': {'col': 'equipo', 'id': 'id'}, 
        'cat_elementos': {'col': 'elemento', 'id': 'id'},
        'accesorios': {'col': 'accesorios', 'id': 'id_equipo'},
        'detalle_revision': {'col': 'descripción', 'id': 'id'},
        'solucion': {'col': 'solución', 'id': 'id'},
        'falla_reportada': {'col': 'falla', 'id': 'id'}
    }

    if tabla not in config:
        return jsonify({"status": "error", "message": "Tabla no válida"}), 400

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        conf = config[tabla]
        
        # Nota: Usamos f-strings solo para nombres de tablas validados por el diccionario 'config'
        cur.execute(f"SELECT {conf['id']} as id, {conf['col']} as nombre FROM {tabla} ORDER BY {conf['id']} ASC;")
        datos = cur.fetchall()
        return jsonify(datos)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn: conn.close()

# --- 5. CREACIÓN DE TICKETS ---
@app.route('/api/tickets/crear', methods=['POST'])
def crear_ticket_interno():
    conn = None
    try:
        datos = request.json
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Generar Folio
        cur.execute("SELECT COUNT(*) FROM tickets")
        count = cur.fetchone()[0]
        nuevo_codigo = f"INT-{count + 1:04d}"

        # Insertar ticket
        cur.execute("""
            INSERT INTO tickets (id_clientes, num_autobus, id_falla_reportada, estado, fecha_creacion, codigo, tipo)
            VALUES (%s, %s, %s, 'ABIERTO', NOW(), %s, 'INTERNO')
            RETURNING id;
        """, (datos['id_cliente'], datos['num_autobus'], datos['id_falla'], nuevo_codigo))
        
        ticket_id = cur.fetchone()[0]
        
        # Vincular técnico en ficha técnica si se proporciona
        if datos.get('id_tecnico'):
            cur.execute("""
                INSERT INTO fichas_tecnicas (id_ticket, id_tecnico, fecha_inicio)
                VALUES (%s, %s, NOW());
            """, (ticket_id, datos['id_tecnico']))

        conn.commit()
        return jsonify({"status": "success", "message": "Ticket creado", "codigo": nuevo_codigo})
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn: conn.close()

# --- 6. FICHAS COMPLETAS ---
@app.route('/api/fichas-completas', methods=['GET'])
def get_fichas_completas():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT 
                f.id as ficha_id, t.codigo as ticket_cod, t.estado,
                (tec.nombre || ' ' || tec.primer_apellido) as tecnico,
                elem.elemento, acc.accesorios as accesorio,
                rev.descripción as detalle_revision, sol.solución,
                f.fecha_inicio, f.fecha_cierre, f.observacion, f.evidencia_url
            FROM fichas_tecnicas f
            JOIN tickets t ON f.id_ticket = t.id
            LEFT JOIN tecnicos tec ON f.id_tecnico = tec.id
            LEFT JOIN cat_elementos elem ON f.id_cat_elementos = elem.id
            LEFT JOIN accesorios acc ON f.id_accesorios = acc.id_equipo
            LEFT JOIN detalle_revision rev ON f.id_detalle_revision = rev.id
            LEFT JOIN solucion sol ON f.id_solucion = sol.id
            ORDER BY f.fecha_inicio DESC;
        """)
        fichas = cur.fetchall()
        return jsonify({"status": "success", "data": fichas})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn: conn.close()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
