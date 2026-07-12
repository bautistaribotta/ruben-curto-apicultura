// Lógica para las notificaciones Toast

/**
 * Crea y muestra un nuevo toast dinámicamente
 * @param {string} mensaje - El texto a mostrar
 * @param {string} tipo - 'success', 'error' o 'info'
 */
function crearToast(mensaje, tipo = 'success') {
    const contenedor = document.getElementById('contenedor-toast');
    if (!contenedor) return;

    // Genero el elemento del toast
    const toast = document.createElement('div');
    toast.className = `toast ${tipo}`;

    // Defino el icono según el tipo de mensaje
    let icono = 'info';
    if (tipo === 'success') icono = 'check_circle';
    if (tipo === 'error') icono = 'error';

    toast.innerHTML = `
        <span class="material-symbols-outlined">${icono}</span>
        <div class="toast-contenido">
            <p>${mensaje}</p>
        </div>
        <button class="btn-cerrar-toast" onclick="cerrarToast(this.parentElement)">
            <span class="material-symbols-outlined">close</span>
        </button>
        <div class="toast-progress"></div>
    `;

    // Lo inserto en el contenedor
    contenedor.appendChild(toast);

    // Configuro el auto-cerrado para que desaparezca en 4 segundos
    setTimeout(() => {
        cerrarToast(toast);
    }, 4000);
}

// Funciones directas para facilitar el uso en otros scripts
function notificarExito(msj) { crearToast(msj, 'success'); }
function notificarError(msj) { crearToast(msj, 'error'); }
function notificarInfo(msj) { crearToast(msj, 'info'); }

// Los errores que frenan una acción ya iniciada (no se pudo crear/eliminar/completar)
// se muestran en el modal central, no como toast. Las validaciones previas de input
// siguen usando notificarError (toast). El modal vive en paneles.js.
function notificarErrorModal(msj) {
    if (typeof abrirModalError === 'function') abrirModalError(msj);
    else alert(msj);
}

/**
 * Cierra un toast con una animación de desvanecimiento
 */
function cerrarToast(toast) {
    if (!toast) return;
    toast.classList.add('desvanecer');
    setTimeout(() => {
        if (toast.parentElement) {
            toast.remove();
        }
    }, 300);
}

// Inicializo los toasts que ya vienen cargados desde el servidor (Django Messages)
function inicializarToasts() {
    const toasts = document.querySelectorAll('.toast');
    toasts.forEach(toast => {
        setTimeout(() => {
            cerrarToast(toast);
        }, 4000);
    });
}

// Los mensajes de error que llegan del servidor (Django messages con tag 'error')
// no se muestran como toast: se juntan y se muestran en el modal central.
function inicializarErroresServidor() {
    const contenedor = document.getElementById('errores-servidor');
    if (!contenedor) return;

    // Uso textContent (no innerText): el contenedor tiene el atributo hidden y en
    // varios motores innerText devuelve '' para elementos no renderizados.
    const mensajes = Array.from(contenedor.querySelectorAll('p'))
        .map(p => p.textContent.trim())
        .filter(Boolean);

    if (mensajes.length === 0) return;

    // Si hay varios errores, los uno en un solo modal (uno por línea)
    if (typeof abrirModalError === 'function') {
        abrirModalError(mensajes.join('\n'));
    }
}

// Lanzo la inicialización cuando el documento está listo
document.addEventListener('DOMContentLoaded', inicializarToasts);
document.addEventListener('DOMContentLoaded', inicializarErroresServidor);