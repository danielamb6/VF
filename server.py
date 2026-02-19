from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import cloudinary
import cloudinary.uploader
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from io import BytesIO
import bcrypt
import os

app = Flask(__name__)
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
        cur.execute("""
            SELECT t.codigo, t.fecha_creacion as fecha, e.empresa, t.estado
            FROM tickets t 
            LEFT JOIN cliente c ON t.id_clientes = c.id
            LEFT JOIN empresas e ON c.id_empresa = e.id
            ORDER BY t.fecha_creacion DESC;
        """)
        tickets = cur.fetchall()
        
        cur.execute("""
            SELECT COUNT(*) as total,
                   COUNT(*) FILTER (WHERE estado = 'ABIERTO') as abiertas,
                   COUNT(*) FILTER (WHERE estado = 'RESUELTO') as resueltos
            FROM tickets;
        """)
        stats = cur.fetchone()
        return jsonify({"status": "success", "tickets": tickets, "stats": stats})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn: conn.close()

# --- 2. TABLA LISTA DE TICKETS INTERNOS (VERSIÓN CORREGIDA) ---
@app.route('/api/tickets-internos', methods=['GET'])
def get_tickets_internos():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT 
                ti.id,
                ti.codigo, 
                COALESCE(sa.nombre, 'Admin') || ' ' || COALESCE(sa.primer_apellido, '') as administrador,
                e.empresa,
                ti.num_autobus,
                TO_CHAR(ti.fecha_creacion, 'DD/MM/YYYY HH24:MI') as fecha_inicio,
                TO_CHAR(ft.fecha_cierre, 'DD/MM/YYYY HH24:MI') as fecha_fin,
                eq.equipo,
                fr.falla as falla_reportada,
                ti.estado,
                CONCAT(tec.nombre, ' ', tec.primer_apellido) as tecnico,
                s.solucion,
                ft.observacion
            FROM tickets_internos ti
            LEFT JOIN super_admin sa ON ti.id_super_admin = sa.id
            LEFT JOIN empresas e ON ti.id_empresa = e.id
            LEFT JOIN falla_reportada fr ON ti.id_falla_reportada = fr.id
            LEFT JOIN equipo eq ON fr.id_equipo = eq.id
            LEFT JOIN fichas_tecnicas ft ON ti.id = ft.id_ticket_interno
            LEFT JOIN tecnicos tec ON ft.id_tecnico = tec.id
            LEFT JOIN solucion s ON ft.id_solucion = s.id
            ORDER BY ti.fecha_creacion DESC;
        """)
        
        tickets = cur.fetchall()
        
        return jsonify({
            "status": "success", 
            "data": tickets,
            "total": len(tickets)
        })
        
    except Exception as e:
        print(f"Error obteniendo tickets internos: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn: conn.close()

# --- 3. TABLA REPORTES EXTRA (VERSIÓN CORREGIDA) ---
@app.route('/api/reportes-extra', methods=['GET'])
def get_reportes_extra():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT 
                re.codigo as codigo_extra, 
                ti.codigo as ficha_origen, 
                eq.equipo, 
                ce.elemento, 
                acc.accesorio,
                dr.descripcion as revision,
                s.solucion,
                re.observacion,
                re.tipo
            FROM reporte_extra re
            LEFT JOIN tickets_internos ti ON re.id_fichaTecnica = ti.id
            LEFT JOIN equipo eq ON re.id_equipo = eq.id
            LEFT JOIN cat_elementos ce ON re.id_cat_elementos = ce.id
            LEFT JOIN accesorios acc ON re.id_accesorios = acc.id
            LEFT JOIN detalle_revision dr ON re.id_detalle_revision = dr.id
            LEFT JOIN solucion s ON re.id_solucion = s.id
            ORDER BY re.id DESC;
        """)
        
        reportes = cur.fetchall()
        
        datos_formateados = []
        for r in reportes:
            datos_formateados.append({
                "codigo_extra": r['codigo_extra'],
                "ficha_origen": r['ficha_origen'],
                "equipo": r['equipo'],
                "elemento": r['elemento'] + (' / ' + r['accesorio'] if r['accesorio'] else ''),
                "revision": r['revision'],
                "solucion": r['solucion'],
                "observacion": r['observacion'],
                "tipo": r['tipo']
            })
        
        return jsonify({
            "status": "success", 
            "data": datos_formateados,
            "total": len(datos_formateados)
        })
    except Exception as e:
        print(f"Error obteniendo reportes extra: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn: conn.close()   

# --- 4. CATÁLOGOS Y FILTROS (EMPRESA, EQUIPO, FALLA) ---
@app.route('/api/catalogos/<string:nombre>', methods=['GET'])
def get_catalogo(nombre):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        if nombre == 'empresas':
            cur.execute("SELECT id, empresa as nombre FROM empresas WHERE activo = true ORDER BY empresa")
        elif nombre == 'equipos':
            cur.execute("SELECT id, equipo as nombre FROM equipo WHERE activo = true ORDER BY equipo")
        elif nombre == 'especialidades':
            cur.execute("SELECT id, especialidad as nombre FROM especialidad WHERE activo = true ORDER BY especialidad")
        elif nombre == 'fallas':
            cur.execute("SELECT id, falla as nombre, id_equipo FROM falla_reportada WHERE activo = true ORDER BY falla")
        elif nombre == 'soluciones':
            cur.execute("SELECT id, solucion as nombre FROM solucion WHERE activo = true ORDER BY solucion")
        else:
            return jsonify({"error": "Catálogo no encontrado"}), 404
        return jsonify(cur.fetchall())
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/fallas-por-equipo/<int:id_equipo>', methods=['GET'])
def get_fallas_por_equipo(id_equipo):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT id, falla 
            FROM falla_reportada 
            WHERE id_equipo = %s AND activo = true 
            ORDER BY falla
        """, (id_equipo,))
        return jsonify(cur.fetchall())
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

# --- 5. CREACIÓN DE TICKET INTERNO ---
@app.route('/api/tickets/interno/crear', methods=['POST'])
def crear_ticket_interno():
    conn = None
    try:
        datos = request.json
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        anio_actual = datetime.now().year
        
        if not datos.get('id_empresa') or not datos.get('num_autobus') or not datos.get('id_falla'):
            return jsonify({"status": "error", "message": "Faltan datos requeridos"}), 400
            
        cur.execute("SELECT empresa FROM empresas WHERE id = %s", (datos['id_empresa'],))
        res_emp = cur.fetchone()
        if not res_emp:
            return jsonify({"status": "error", "message": "Empresa no encontrada"}), 404
            
        siglas = res_emp['empresa'][:4].upper() if res_emp else "INTE"
        
        cur.execute("SELECT COUNT(*) as count FROM tickets_internos")
        count = cur.fetchone()['count']
        nuevo_folio = f"{anio_actual}-{siglas}-I-{count + 1:05d}"

        cur.execute("""
            INSERT INTO tickets_internos 
            (id_super_admin, id_empresa, num_autobus, id_falla_reportada, codigo, estado, tipo, fecha_creacion) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            RETURNING id;
        """, (
            datos.get('id_super_admin', 1),
            datos['id_empresa'], 
            datos['num_autobus'], 
            datos['id_falla'], 
            nuevo_folio,
            'ABIERTO',
            'INTERNO'
        ))
        
        nuevo_id = cur.fetchone()['id']
        conn.commit()
        
        return jsonify({
            "status": "success", 
            "codigo": nuevo_folio,
            "id": nuevo_id,
            "message": "Ticket creado exitosamente"
        })
        
    except Exception as e:
        if conn: conn.rollback()
        print(f"Error creando ticket interno: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn: conn.close()

# --- 6. ENDPOINTS PARA TICKETS INTERNOS (CRUD) ---
@app.route('/api/tickets-internos/<int:id>/estado', methods=['PUT'])
def actualizar_estado_ticket_interno(id):
    conn = None
    try:
        datos = request.json
        nuevo_estado = datos.get('estado')
        
        if not nuevo_estado:
            return jsonify({"status": "error", "message": "Estado no proporcionado"}), 400
            
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            UPDATE tickets_internos 
            SET estado = %s 
            WHERE id = %s
            RETURNING id
        """, (nuevo_estado, id))
        
        resultado = cur.fetchone()
        conn.commit()
        
        if resultado:
            return jsonify({"status": "success", "message": f"Estado actualizado a {nuevo_estado}"})
        else:
            return jsonify({"status": "error", "message": "Ticket no encontrado"}), 404
            
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn: conn.close()

@app.route('/api/tickets-internos/<int:id>', methods=['GET'])
def get_ticket_interno_by_id(id):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT 
                ti.id,
                ti.codigo, 
                ti.num_autobus,
                ti.estado,
                TO_CHAR(ti.fecha_creacion, 'DD/MM/YYYY HH24:MI') as fecha_creacion,
                e.id as id_empresa,
                e.empresa,
                fr.id as id_falla,
                fr.falla,
                eq.id as id_equipo,
                eq.equipo,
                sa.id as id_super_admin,
                COALESCE(sa.nombre, 'Admin') as admin_nombre,
                COALESCE(sa.primer_apellido, '') as admin_apellido
            FROM tickets_internos ti
            LEFT JOIN super_admin sa ON ti.id_super_admin = sa.id
            LEFT JOIN empresas e ON ti.id_empresa = e.id
            LEFT JOIN falla_reportada fr ON ti.id_falla_reportada = fr.id
            LEFT JOIN equipo eq ON fr.id_equipo = eq.id
            WHERE ti.id = %s;
        """, (id,))
        
        ticket = cur.fetchone()
        
        if not ticket:
            return jsonify({"status": "error", "message": "Ticket no encontrado"}), 404
            
        return jsonify({"status": "success", "data": ticket})
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn: conn.close()

# --- 7. CLIENTES ---
@app.route('/api/clientes-detallados', methods=['GET'])
def get_clientes_detallados():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT c.id, c.id_telegram, c.nombre, c.primer_apellido, c.segundo_apellido,
                   e.empresa as nombre_empresa, c.activo
            FROM cliente c
            LEFT JOIN empresas e ON c.id_empresa = e.id
            ORDER BY c.id DESC;
        """)
        return jsonify({"status": "success", "data": cur.fetchall()})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn: conn.close()

@app.route('/api/clientes/<int:id>/toggle-status', methods=['POST'])
def toggle_cliente_status(id):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT activo FROM cliente WHERE id = %s", (id,))
        cliente = cur.fetchone()
        
        if not cliente:
            return jsonify({"status": "error", "message": "Cliente no encontrado"}), 404
            
        nuevo_estado = not cliente['activo']
        cur.execute("UPDATE cliente SET activo = %s WHERE id = %s", (nuevo_estado, id))
        conn.commit()
        
        return jsonify({
            "status": "success",
            "nuevo_estado": nuevo_estado,
            "message": f"Cliente {'activado' if nuevo_estado else 'desactivado'} correctamente"
        })
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn: conn.close()

# --- 8. TÉCNICOS ---
@app.route('/api/tecnicos-detallados', methods=['GET'])
def get_tecnicos_detallados():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT t.id, t.id_telegram, t.nombre, t.primer_apellido, t.segundo_apellido,
                   e.especialidad as nombre_especialidad, t.activo
            FROM tecnicos t
            LEFT JOIN especialidad e ON t.id_especialidad = e.id
            ORDER BY t.id DESC;
        """)
        return jsonify({"status": "success", "data": cur.fetchall()})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn: conn.close()

@app.route('/api/tecnicos/<int:id>/toggle-status', methods=['POST'])
def toggle_tecnico_status(id):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT activo FROM tecnicos WHERE id = %s", (id,))
        tecnico = cur.fetchone()
        
        if not tecnico:
            return jsonify({"status": "error", "message": "Técnico no encontrado"}), 404
            
        nuevo_estado = not tecnico['activo']
        cur.execute("UPDATE tecnicos SET activo = %s WHERE id = %s", (nuevo_estado, id))
        conn.commit()
        
        return jsonify({
            "status": "success",
            "nuevo_estado": nuevo_estado,
            "message": f"Técnico {'activado' if nuevo_estado else 'desactivado'} correctamente"
        })
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn: conn.close()

# --- 9. INCIDENCIAS (FICHAS TÉCNICAS) ---
@app.route('/api/fichas-completas', methods=['GET'])
def get_fichas_completas():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        query = """
            SELECT ft.id, t.codigo as ticket_cod, e.empresa as empresa_nombre,
                CONCAT(tec.nombre, ' ', tec.primer_apellido) as tecnico,
                eq.equipo as equipo_nombre, fr.falla as falla_reportada,
                s.solucion as detalle_solucion, t.estado,
                COALESCE(ft.evidencia_url, t.evidencia_url) as evidencia_url,
                ft.fecha_inicio
            FROM fichas_tecnicas ft
            LEFT JOIN tickets t ON ft.id_ticket = t.id
            LEFT JOIN cliente c ON t.id_clientes = c.id
            LEFT JOIN empresas e ON c.id_empresa = e.id
            LEFT JOIN tecnicos tec ON ft.id_tecnico = tec.id
            LEFT JOIN falla_reportada fr ON t.id_falla_reportada = fr.id
            LEFT JOIN equipo eq ON fr.id_equipo = eq.id
            LEFT JOIN solucion s ON ft.id_solucion = s.id
            ORDER BY ft.fecha_inicio DESC NULLS LAST;
        """
        cur.execute(query)
        return jsonify({"status": "success", "data": cur.fetchall()})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn: conn.close()

# --- 10. EVIDENCIAS (CLOUDINARY) ---
@app.route('/api/upload-evidencia', methods=['POST'])
def upload_evidencia():
    cloudinary.config(
        cloud_name='dnfx1hrw1',
        api_key='718896728199423',
        api_secret='n7y6f0_Ps3I79vJgaz6pDuplc2E',
        secure=True
    )
    try:
        if 'file' not in request.files:
            return jsonify({"status": "error", "message": "No se envió ningún archivo"}), 400
        file = request.files['file']
        upload_result = cloudinary.uploader.upload(file, folder="incidencias/")
        return jsonify({"status": "success", "url": upload_result['secure_url']})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# --- 11. ADMINISTRACIÓN DE USUARIOS ---
@app.route('/api/admin', methods=['POST'])
def registrar_usuario():
    datos = request.json
    rol_seleccionado = datos.get('rol') 
    
    mapeo_config = {
        'super_admin': {'tabla': 'super_admin', 'rol_db': 'super_admin'},
        'supervisor': {'tabla': 'supervisor', 'rol_db': 'supervisor'},
        'emp_admin': {'tabla': 'emp_admin', 'rol_db': 'emp_admin'}
    }
    
    config = mapeo_config.get(rol_seleccionado)
    if not config:
        return jsonify({"error": "Rol no válido"}), 400

    password_hash = bcrypt.hashpw(datos['password'].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        if rol_seleccionado == 'emp_admin':
            if not datos.get('id_empresa'):
                return jsonify({"error": "El ID de empresa es obligatorio para este rol"}), 400
                
            query = """
                INSERT INTO emp_admin 
                (id_empresa, nombre, primer_apellido, segundo_apellido, usuario, contrasena, rol, correo, activo, created_at, updated_at) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, true, NOW(), NOW())
            """
            cur.execute(query, (
                datos['id_empresa'], datos['nombre'], datos['primer_apellido'], 
                datos.get('segundo_apellido', ''), datos['username'], password_hash, 
                'emp_admin', datos['email']
            ))
        else:
            query = f"INSERT INTO {config['tabla']} (nombre, primer_apellido, segundo_apellido, usuario, contrasena, rol, correo) VALUES (%s, %s, %s, %s, %s, %s, %s)"
            cur.execute(query, (
                datos['nombre'], datos['primer_apellido'], 
                datos.get('segundo_apellido', ''), datos['username'], 
                password_hash, config['rol_db'], datos['email']
            ))
            
        conn.commit()
        return jsonify({"status": "success", "message": "Usuario creado correctamente"})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/api/admin', methods=['GET'])
def obtener_todos_los_usuarios():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        query = """
            SELECT id, nombre, primer_apellido, segundo_apellido, usuario, correo, rol, activo, 
                   NULL as id_empresa, 'SISTEMA' as nombre_empresa, NULL as created_at 
            FROM super_admin
            UNION ALL
            SELECT id, nombre, primer_apellido, segundo_apellido, usuario, correo, rol, activo, 
                   NULL as id_empresa, 'SISTEMA' as nombre_empresa, NULL as created_at 
            FROM supervisor
            UNION ALL
            SELECT a.id, a.nombre, a.primer_apellido, a.segundo_apellido, a.usuario, a.correo, a.rol, a.activo, 
                   a.id_empresa, e.empresa as nombre_empresa, a.created_at 
            FROM emp_admin a
            LEFT JOIN empresas e ON a.id_empresa = e.id
            ORDER BY nombre ASC;
        """
        cur.execute(query)
        usuarios = cur.fetchall()
        return jsonify(usuarios)
    except Exception as e:
        print(f"Error en SQL: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()

# --- 12. CATÁLOGOS CRUD COMPLETO ---
@app.route('/api/catalogos/<tabla>', methods=['GET'])
def obtener_catalogos(tabla):
    tablas_permitidas = {
        'equipo': 'equipo',
        'empresas': 'empresa',
        'cat_elementos': 'elemento',
        'falla_reportada': 'falla',
        'solucion': 'solucion',
        'detalle_revision': 'descripcion',
        'especialidad': 'especialidad',
        'accesorios': 'accesorio'
    }
    
    if tabla not in tablas_permitidas:
        return jsonify({"error": "Catálogo no válido"}), 400

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        nombre_columna = tablas_permitidas[tabla]
        query = f"SELECT id, {nombre_columna} as nombre, activo FROM {tabla} ORDER BY id DESC"
        cur.execute(query)
        return jsonify(cur.fetchall())
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/catalogos/<tabla>', methods=['POST'])
def agregar_catalogo(tabla):
    tablas_permitidas = ['equipo', 'empresas', 'cat_elementos', 'falla_reportada', 'solucion', 'detalle_revision', 'especialidad', 'accesorios']
    if tabla not in tablas_permitidas:
        return jsonify({"error": "Catálogo no válido"}), 400

    datos = request.json
    nombre = datos.get('nombre')
    if not nombre:
        return jsonify({"error": "El nombre es requerido"}), 400
        
    col_map = {
        'equipo': 'equipo', 
        'empresas': 'empresa', 
        'falla_reportada': 'falla',
        'solucion': 'solucion', 
        'detalle_revision': 'descripcion', 
        'cat_elementos': 'elemento',
        'especialidad': 'especialidad',
        'accesorios': 'accesorio'
    }

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        if tabla == 'equipo' and datos.get('id_especialidad'):
            cur.execute(f"INSERT INTO {tabla} ({col_map[tabla]}, id_especialidad, activo) VALUES (%s, %s, true)", 
                        (nombre, datos.get('id_especialidad')))
        elif tabla == 'falla_reportada' and datos.get('id_equipo'):
            cur.execute(f"INSERT INTO {tabla} ({col_map[tabla]}, id_equipo, activo) VALUES (%s, %s, true)", 
                        (nombre, datos.get('id_equipo')))
        else:
            cur.execute(f"INSERT INTO {tabla} ({col_map[tabla]}, activo) VALUES (%s, true)", (nombre,))
            
        conn.commit()
        return jsonify({"status": "success", "message": "Registro agregado correctamente"}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/catalogos/<tabla>/<int:id>', methods=['PUT'])
def actualizar_catalogo(tabla, id):
    datos = request.json
    nombre = datos.get('nombre')
    if not nombre:
        return jsonify({"error": "El nombre es requerido"}), 400
        
    col_map = {
        'equipo': 'equipo', 'empresas': 'empresa', 'falla_reportada': 'falla',
        'solucion': 'solucion', 'detalle_revision': 'descripcion', 'cat_elementos': 'elemento',
        'especialidad': 'especialidad', 'accesorios': 'accesorio'
    }
    
    if tabla not in col_map:
        return jsonify({"error": "Catálogo no válido"}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        columna = col_map[tabla]
        cur.execute(f"UPDATE {tabla} SET {columna} = %s WHERE id = %s", (nombre, id))
        conn.commit()
        return jsonify({"status": "success", "message": "Registro actualizado correctamente"})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/catalogos/<tabla>/<int:id>/toggle', methods=['POST'])
def toggle_catalogo(tabla, id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(f"UPDATE {tabla} SET activo = NOT activo WHERE id = %s RETURNING activo", (id,))
        nuevo_estado = cur.fetchone()[0]
        conn.commit()
        return jsonify({
            "status": "success", 
            "activo": nuevo_estado,
            "message": f"Registro {'activado' if nuevo_estado else 'desactivado'} correctamente"
        })
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/catalogos/equipos-con-especialidades', methods=['GET'])
def get_equipos_con_especialidades():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT e.id, e.equipo, es.id as id_especialidad, es.especialidad
            FROM equipo e
            LEFT JOIN especialidad es ON e.id_especialidad = es.id
            WHERE e.activo = true
            ORDER BY e.equipo
        """)
        return jsonify(cur.fetchall())
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

# --- 13. EXPORTACIÓN PDF ---
@app.route('/api/generar-pdf/<string:tipo>', methods=['GET'])
def generar_pdf(tipo):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(letter))
        elements = []
        styles = getSampleStyleSheet()
        
        elements.append(Paragraph(f"Reporte de {tipo.capitalize()}", styles['Heading1']))
        elements.append(Spacer(1, 0.2*inch))
        
        doc.build(elements)
        buffer.seek(0)
        return send_file(
            buffer, 
            as_attachment=True, 
            download_name=f"reporte_{tipo}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf", 
            mimetype='application/pdf'
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn: conn.close()

# --- 14. ENDPOINT PARA PDF DE TICKET INDIVIDUAL ---
@app.route('/api/ticket/<string:codigo>/pdf', methods=['GET'])
def generar_pdf_ticket(codigo):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    
    elements.append(Paragraph(f"Ticket: {codigo}", styles['Heading1']))
    doc.build(elements)
    buffer.seek(0)
    
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"ticket_{codigo}.pdf",
        mimetype='application/pdf'
    )

# --- 15. NUEVOS ENDPOINTS PARA REPORTES ---

@app.route('/api/tickets-completos', methods=['GET'])
def get_tickets_completos():
    """Obtiene todos los tickets (externos) con información completa"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT 
                t.id,
                t.codigo,
                t.num_autobus,
                t.estado,
                TO_CHAR(t.fecha_creacion, 'DD/MM/YYYY HH24:MI') as fecha_creacion,
                e.empresa,
                CONCAT(c.nombre, ' ', c.primer_apellido) as cliente,
                eq.equipo,
                fr.falla,
                t.evidencia_url,
                t.tipo
            FROM tickets t
            LEFT JOIN cliente c ON t.id_clientes = c.id
            LEFT JOIN empresas e ON c.id_empresa = e.id
            LEFT JOIN falla_reportada fr ON t.id_falla_reportada = fr.id
            LEFT JOIN equipo eq ON fr.id_equipo = eq.id
            ORDER BY t.fecha_creacion DESC;
        """)
        
        tickets = cur.fetchall()
        return jsonify({"status": "success", "data": tickets, "total": len(tickets)})
        
    except Exception as e:
        print(f"Error obteniendo tickets completos: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn: conn.close()

@app.route('/api/tickets-internos-completos', methods=['GET'])
def get_tickets_internos_completos():
    """Obtiene todos los tickets internos con información completa"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT 
                ti.id,
                ti.codigo,
                ti.num_autobus,
                ti.estado,
                TO_CHAR(ti.fecha_creacion, 'DD/MM/YYYY HH24:MI') as fecha_creacion,
                e.empresa,
                CONCAT(sa.nombre, ' ', sa.primer_apellido) as super_admin,
                eq.equipo,
                fr.falla,
                ti.tipo
            FROM tickets_internos ti
            LEFT JOIN super_admin sa ON ti.id_super_admin = sa.id
            LEFT JOIN empresas e ON ti.id_empresa = e.id
            LEFT JOIN falla_reportada fr ON ti.id_falla_reportada = fr.id
            LEFT JOIN equipo eq ON fr.id_equipo = eq.id
            ORDER BY ti.fecha_creacion DESC;
        """)
        
        tickets = cur.fetchall()
        return jsonify({"status": "success", "data": tickets, "total": len(tickets)})
        
    except Exception as e:
        print(f"Error obteniendo tickets internos completos: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn: conn.close()

@app.route('/api/fichas-tecnicas-completas', methods=['GET'])
def get_fichas_tecnicas_completas():
    """Obtiene todas las fichas técnicas con información completa"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT 
                ft.id,
                t.codigo as ticket_codigo,
                ti.codigo as ticket_interno_codigo,
                CONCAT(tec.nombre, ' ', tec.primer_apellido) as tecnico,
                TO_CHAR(ft.fecha_inicio, 'DD/MM/YYYY HH24:MI') as fecha_inicio,
                TO_CHAR(ft.fecha_cierre, 'DD/MM/YYYY HH24:MI') as fecha_cierre,
                eq.equipo,
                ce.elemento,
                acc.accesorio,
                dr.descripcion as detalle_revision,
                s.solucion,
                ft.observacion,
                ft.evidencia_url,
                ST_AsText(ft.ubicacion_atencion) as ubicacion
            FROM fichas_tecnicas ft
            LEFT JOIN tickets t ON ft.id_ticket = t.id
            LEFT JOIN tickets_internos ti ON ft.id_ticket_interno = ti.id
            LEFT JOIN tecnicos tec ON ft.id_tecnico = tec.id
            LEFT JOIN equipo eq ON ft.id_equipo = eq.id
            LEFT JOIN cat_elementos ce ON ft.id_cat_elementos = ce.id
            LEFT JOIN accesorios acc ON ft.id_accesorios = acc.id
            LEFT JOIN detalle_revision dr ON ft.id_detalle_revision = dr.id
            LEFT JOIN solucion s ON ft.id_solucion = s.id
            ORDER BY ft.fecha_inicio DESC NULLS LAST;
        """)
        
        fichas = cur.fetchall()
        return jsonify({"status": "success", "data": fichas, "total": len(fichas)})
        
    except Exception as e:
        print(f"Error obteniendo fichas técnicas: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn: conn.close()

@app.route('/api/reportes-extra-completos', methods=['GET'])
def get_reportes_extra_completos():
    """Obtiene todos los reportes extra con información completa"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT 
                re.id,
                re.codigo,
                t.codigo as ticket_codigo,
                ti.codigo as ticket_interno_codigo,
                eq.equipo,
                ce.elemento,
                acc.accesorio,
                dr.descripcion as detalle_revision,
                s.solucion,
                re.observacion,
                re.tipo
            FROM reporte_extra re
            LEFT JOIN fichas_tecnicas ft ON re.id_fichaTecnica = ft.id
            LEFT JOIN tickets t ON ft.id_ticket = t.id
            LEFT JOIN tickets_internos ti ON ft.id_ticket_interno = ti.id
            LEFT JOIN equipo eq ON re.id_equipo = eq.id
            LEFT JOIN cat_elementos ce ON re.id_cat_elementos = ce.id
            LEFT JOIN accesorios acc ON re.id_accesorios = acc.id
            LEFT JOIN detalle_revision dr ON re.id_detalle_revision = dr.id
            LEFT JOIN solucion s ON re.id_solucion = s.id
            ORDER BY re.id DESC;
        """)
        
        reportes = cur.fetchall()
        return jsonify({"status": "success", "data": reportes, "total": len(reportes)})
        
    except Exception as e:
        print(f"Error obteniendo reportes extra: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn: conn.close()

@app.route('/api/reporte-general-completo', methods=['GET'])
def get_reporte_general_completo():
    """Obtiene todos los datos necesarios para el reporte general"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # 1. Obtener tickets externos
        cur.execute("""
            SELECT 
                t.id,
                t.codigo,
                t.num_autobus,
                t.estado,
                TO_CHAR(t.fecha_creacion, 'DD/MM/YYYY HH24:MI') as fecha_creacion,
                e.empresa,
                CONCAT(c.nombre, ' ', c.primer_apellido) as cliente,
                eq.equipo,
                fr.falla,
                t.tipo
            FROM tickets t
            LEFT JOIN cliente c ON t.id_clientes = c.id
            LEFT JOIN empresas e ON c.id_empresa = e.id
            LEFT JOIN falla_reportada fr ON t.id_falla_reportada = fr.id
            LEFT JOIN equipo eq ON fr.id_equipo = eq.id
            ORDER BY t.fecha_creacion DESC;
        """)
        tickets_externos = cur.fetchall()
        
        # 2. Obtener tickets internos
        cur.execute("""
            SELECT 
                ti.id,
                ti.codigo,
                ti.num_autobus,
                ti.estado,
                TO_CHAR(ti.fecha_creacion, 'DD/MM/YYYY HH24:MI') as fecha_creacion,
                e.empresa,
                CONCAT(sa.nombre, ' ', sa.primer_apellido) as super_admin,
                eq.equipo,
                fr.falla,
                ti.tipo
            FROM tickets_internos ti
            LEFT JOIN super_admin sa ON ti.id_super_admin = sa.id
            LEFT JOIN empresas e ON ti.id_empresa = e.id
            LEFT JOIN falla_reportada fr ON ti.id_falla_reportada = fr.id
            LEFT JOIN equipo eq ON fr.id_equipo = eq.id
            ORDER BY ti.fecha_creacion DESC;
        """)
        tickets_internos = cur.fetchall()
        
        # 3. Obtener fichas técnicas
        cur.execute("""
            SELECT 
                ft.id,
                COALESCE(t.codigo, ti.codigo) as ticket_origen,
                CONCAT(tec.nombre, ' ', tec.primer_apellido) as tecnico,
                TO_CHAR(ft.fecha_inicio, 'DD/MM/YYYY HH24:MI') as fecha_inicio,
                TO_CHAR(ft.fecha_cierre, 'DD/MM/YYYY HH24:MI') as fecha_cierre,
                eq.equipo,
                ce.elemento,
                dr.descripcion as detalle_revision,
                s.solucion,
                ft.observacion
            FROM fichas_tecnicas ft
            LEFT JOIN tickets t ON ft.id_ticket = t.id
            LEFT JOIN tickets_internos ti ON ft.id_ticket_interno = ti.id
            LEFT JOIN tecnicos tec ON ft.id_tecnico = tec.id
            LEFT JOIN equipo eq ON ft.id_equipo = eq.id
            LEFT JOIN cat_elementos ce ON ft.id_cat_elementos = ce.id
            LEFT JOIN detalle_revision dr ON ft.id_detalle_revision = dr.id
            LEFT JOIN solucion s ON ft.id_solucion = s.id
            ORDER BY ft.fecha_inicio DESC NULLS LAST;
        """)
        fichas_tecnicas = cur.fetchall()
        
        # 4. Obtener reportes extra
        cur.execute("""
            SELECT 
                re.id,
                re.codigo,
                COALESCE(t.codigo, ti.codigo) as ticket_origen,
                eq.equipo,
                ce.elemento,
                dr.descripcion as detalle_revision,
                s.solucion,
                re.observacion,
                re.tipo
            FROM reporte_extra re
            LEFT JOIN fichas_tecnicas ft ON re.id_fichaTecnica = ft.id
            LEFT JOIN tickets t ON ft.id_ticket = t.id
            LEFT JOIN tickets_internos ti ON ft.id_ticket_interno = ti.id
            LEFT JOIN equipo eq ON re.id_equipo = eq.id
            LEFT JOIN cat_elementos ce ON re.id_cat_elementos = ce.id
            LEFT JOIN detalle_revision dr ON re.id_detalle_revision = dr.id
            LEFT JOIN solucion s ON re.id_solucion = s.id
            ORDER BY re.id DESC;
        """)
        reportes_extra = cur.fetchall()
        
        # 5. Estadísticas generales
        cur.execute("""
            SELECT 
                (SELECT COUNT(*) FROM tickets) as total_tickets_externos,
                (SELECT COUNT(*) FROM tickets_internos) as total_tickets_internos,
                (SELECT COUNT(*) FROM tickets WHERE estado = 'ABIERTO') as externos_abiertos,
                (SELECT COUNT(*) FROM tickets_internos WHERE estado = 'ABIERTO') as internos_abiertos,
                (SELECT COUNT(*) FROM tickets WHERE estado = 'RESUELTO') as externos_resueltos,
                (SELECT COUNT(*) FROM tickets_internos WHERE estado = 'RESUELTO') as internos_resueltos,
                (SELECT COUNT(*) FROM fichas_tecnicas) as total_fichas,
                (SELECT COUNT(*) FROM reporte_extra) as total_reportes_extra;
        """)
        stats = cur.fetchone()
        
        return jsonify({
            "status": "success",
            "data": {
                "tickets_externos": tickets_externos,
                "tickets_internos": tickets_internos,
                "fichas_tecnicas": fichas_tecnicas,
                "reportes_extra": reportes_extra,
                "stats": stats
            }
        })
        
    except Exception as e:
        print(f"Error obteniendo reporte general: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn: conn.close()
