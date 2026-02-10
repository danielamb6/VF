const API_URL = "http://localhost:5000/api";

document.addEventListener('DOMContentLoaded', function() {
    const sesion = localStorage.getItem('sesion');
    if (!sesion) {
        window.location.href = "login.html";
        return;
    }
    
    // Carga inicial del Dashboard
    cargarDatosDashboard();
    configurarNavegacion();
});

/**
 * Control de navegación: Muestra vistas y dispara la carga de datos
 */
function configurarNavegacion() {
    const navLinks = document.querySelectorAll('.menu-link');
    const views = document.querySelectorAll('main > div');

    navLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            if(!this.id || !this.id.startsWith('nav-')) return;
            
            e.preventDefault();
            navLinks.forEach(nl => nl.classList.remove('active'));
            this.classList.add('active');
            
            views.forEach(v => v.style.display = 'none');
            const targetId = 'view-' + this.id.split('-')[1];
            const targetView = document.getElementById(targetId);
            
            if(targetView) {
                targetView.style.display = 'block';
                
                // DISPARADORES DE CARGA SEGÚN SECCIÓN
                switch(targetId) {
                    case 'view-dashboard':
                        cargarDatosDashboard();
                        break;
                    case 'view-incidencias':
                        cargarFichasTecnicas();
                        break;
                    case 'view-clientes':
                        cargarClientesDesdeBD();
                        break;
                    case 'view-tecnicos':
                        cargarTecnicosDesdeBD();
                        break;
                    case 'view-catalogos':
                        cargarTodosLosCatalogos();
                        break;
                    case 'view-crearticket':
                        cargarSelectsTicket();
                        break;
                }
            }
        });
    });
}

// --- 1. DASHBOARD GENERAL ---
async function cargarDatosDashboard() {
    try {
        const respuesta = await fetch(`${API_URL}/dashboard-data`);
        const data = await respuesta.json();
        
        if (data.status === "success") {
            // Actualizar contadores (KPIs)
            document.getElementById('total-incidencias').textContent = data.stats.total;
            document.getElementById('abiertas-count').textContent = data.stats.abiertas;
            document.getElementById('atencion-count').textContent = data.stats.atencion;
            document.getElementById('espera-refaccion-count').textContent = data.stats.espera;
            document.getElementById('resueltos-count').textContent = data.stats.resueltos;
            
            // Nuevos contadores solicitados
            document.getElementById('total-tecnicos').textContent = data.stats.total_tecnicos;
            document.getElementById('total-clientes').textContent = data.stats.total_clientes;
            document.getElementById('total-empresas').textContent = data.stats.total_empresas;

            const tbody = document.getElementById('all-tickets-body');
            tbody.innerHTML = data.tickets.map(t => `
                <tr class="dashboard-row">
                    <td><span class="folio-label">${t.codigo}</span></td>
                    <td>${new Date(t.fecha).toLocaleDateString()}</td>
                    <td><strong>${t.empresa || 'N/A'}</strong></td>
                    <td><span class="status-badge ${t.estado.toLowerCase().replace(/\s+/g, '-')}">${t.estado}</span></td>
                </tr>
            `).join('');
        }
    } catch (e) { console.error("Error Dashboard:", e); }
}

// --- 2. LISTADO DE TÉCNICOS ---
async function cargarTecnicosDesdeBD() {
    const tbody = document.getElementById('tecnicos-especialidad-body');
    if (!tbody) return;

    try {
        const res = await fetch(`${API_URL}/tecnicos-detallados`);
        const tecnicos = await res.json();

        tbody.innerHTML = tecnicos.map(t => `
            <tr>
                <td><strong>${t.nombre} ${t.primer_apellido}</strong></td>
                <td><span class="spec-tag">${t.nombre_especialidad || 'General'}</span></td>
                <td><i class="fab fa-telegram-plane"></i> ${t.id_telegram || 'S/V'}</td>
                <td>
                    <span class="badge ${t.activo ? 'active' : 'inactive'}">
                        ${t.activo ? 'ACTIVO' : 'INACTIVO'}
                    </span>
                </td>
            </tr>
        `).join('');
    } catch (e) { console.error("Error Técnicos:", e); }
}

// --- 3. LISTADO DE CLIENTES ---
async function cargarClientesDesdeBD() {
    const tbody = document.getElementById('clientes-list-body');
    if (!tbody) return;

    try {
        const res = await fetch(`${API_URL}/clientes-detallados`);
        const clientes = await res.json();

        tbody.innerHTML = clientes.map(c => `
            <tr>
                <td>#${c.id}</td>
                <td><i class="fab fa-telegram-plane"></i> ${c.id_telegram || 'N/A'}</td>
                <td>${c.nombre} ${c.primer_apellido}</td>
                <td><span class="company-tag">${c.nombre_empresa || 'N/A'}</span></td>
                <td><span class="badge ${c.activo ? 'active' : 'inactive'}">${c.activo ? 'ACTIVO' : 'INACTIVO'}</span></td>
            </tr>
        `).join('');
    } catch (e) { console.error("Error Clientes:", e); }
}

// --- 4. CATÁLOGOS TIPO DASHBOARD ---
async function cargarTodosLosCatalogos() {
    const catalogos = {
        'empresas': 'list-empresas',
        'equipo': 'list-equipo',
        'cat_elementos': 'list-elementos',
        'falla_reportada': 'list-fallas',
        'solucion': 'list-soluciones'
    };

    for (const [ruta, idLista] of Object.entries(catalogos)) {
        try {
            const res = await fetch(`${API_URL}/catalogos/${ruta}`);
            const datos = await res.json();
            const listaUI = document.getElementById(idLista);
            
            if (listaUI) {
                listaUI.innerHTML = datos.map(item => `
                    <li class="dashboard-list-li" style="display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #eee;">
                        <span style="font-size: 0.85rem;">${item.nombre.toUpperCase()}</span> 
                        <button class="btn-delete-item" style="color: #e74c3c; background: none; border: none; cursor: pointer;" 
                                onclick="eliminarDelCatalogo('${ruta}', ${item.id})">
                            <i class="fas fa-trash-alt"></i>
                        </button>
                    </li>
                `).join('');
            }
        } catch (error) { console.error(`Error Catálogo ${ruta}:`, error); }
    }
}

// --- 5. FUNCIONES AUXILIARES ---
async function eliminarDelCatalogo(tabla, id) {
    if (!confirm('¿Desea eliminar este registro permanentemente?')) return;
    try {
        const res = await fetch(`${API_URL}/catalogos/${tabla}/${id}`, { method: 'DELETE' });
        if (res.ok) cargarTodosLosCatalogos();
    } catch (e) { alert("Error al eliminar"); }
}

document.getElementById('btn-logout').addEventListener('click', function() {
    localStorage.removeItem('sesion');
    window.location.href = "login.html";
});
