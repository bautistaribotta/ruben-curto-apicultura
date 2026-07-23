// Funciones para abrir y cerrar el panel lateral en productos y clientes
/* Estas funciones le agregan o le quitan la clase "slide-over-abierto" al elemento con el id correspondiente */
function abrirSlideOver(idContenedor = 'contenedor-slide-over') {
    document.getElementById(idContenedor).classList.add('slide-over-abierto');
    document.body.style.overflow = 'hidden';
}

function cerrarSlideOver(idContenedor = 'contenedor-slide-over') {
    const contenedor = document.getElementById(idContenedor);
    contenedor.classList.remove('slide-over-abierto');
    document.body.style.overflow = 'auto';

    // Buscamos si hay un formulario dentro de este panel específico
    const formulario = contenedor.querySelector('form');
    if (formulario) {
        // Limpiamos los datos del formulario al cerrarlo (resetea inputs, selects, etc)
        formulario.reset();
        
        // Si el formulario tiene campos ocultos (como id_cliente o id_producto para edición), los vaciamos
        const camposOcultos = formulario.querySelectorAll('input[type="hidden"]');
        camposOcultos.forEach(campo => {
            // No vaciamos los tokens de seguridad ni el campo de "accion" que rutea la vista
            if (campo.name !== 'csrfmiddlewaretoken' && campo.name !== 'accion') {
                campo.value = '';
            }
        });
    }

    // LÓGICA ESPECÍFICA PARA EL MODAL DE VIAJES:
    // Si cerramos el modal de viaje, debemos borrar todos los inputs de destinos extra
    if (idContenedor === 'slide-over-viaje') {
        const contenedorDestinos = document.getElementById('contenedor-destinos');
        if (contenedorDestinos) {
            // Buscamos todos los inputs dentro del contenedor
            const inputsDestino = contenedorDestinos.querySelectorAll('input[name="destino"]');
            // Si hay más de 1, eliminamos desde el segundo en adelante
            if (inputsDestino.length > 1) {
                for (let i = 1; i < inputsDestino.length; i++) {
                    inputsDestino[i].remove();
                }
            }
            // Ocultamos el botón de quitar destino
            const btnQuitarDestino = document.getElementById('btn-quitar-destino');
            if (btnQuitarDestino) {
                btnQuitarDestino.style.display = 'none';
            }
        }
        
        // Volvemos a popular la fecha de inicio por defecto
        const inputFechaInicio = document.getElementById('fecha-inicio-viaje');
        if (inputFechaInicio) {
            const hoy = new Date().toISOString().split('T')[0];
            inputFechaInicio.value = hoy;
        }
    }

    // LÓGICA ESPECÍFICA PARA EL MODAL DE REPARTOS (Mercado Libre):
    // El destino sale de un select del catalogo, asi que no hay inputs extra que
    // limpiar; solo hay que devolver la fecha al valor por defecto.
    if (idContenedor === 'slide-over-reparto') {
        const inputFechaReparto = document.getElementById('fecha-viaje-reparto');
        if (inputFechaReparto) {
            inputFechaReparto.value = new Date().toISOString().split('T')[0];
        }
    }

    // LÓGICA ESPECÍFICA PARA EL MODAL DE ACOPIOS (Viajes de cereales):
    // Misma limpieza de destinos extra que el modal de viajes
    if (idContenedor === 'slide-over-acopio') {
        const contenedorDestinos = document.getElementById('contenedor-destinos-acopio');
        if (contenedorDestinos) {
            const inputsDestino = contenedorDestinos.querySelectorAll('input[name="destino"]');
            if (inputsDestino.length > 1) {
                for (let i = 1; i < inputsDestino.length; i++) {
                    inputsDestino[i].remove();
                }
            }
            const btnQuitarDestino = document.getElementById('btn-quitar-destino-acopio');
            if (btnQuitarDestino) {
                btnQuitarDestino.style.display = 'none';
            }
        }

        // Volvemos a popular la fecha del viaje por defecto
        const inputFechaAcopio = document.getElementById('fecha-acopio');
        if (inputFechaAcopio) {
            inputFechaAcopio.value = new Date().toISOString().split('T')[0];
        }
    }
}

// Modal de error global (vive en base.html, disponible en todas las vistas)
// Se abre con el motivo del error y solo se cierra con el botón "Entendido"
function abrirModalError(motivo) {
    document.getElementById('texto-modal-error').innerText = motivo;
    document.getElementById('contenedor-modal-error').classList.add('abierto');
    document.body.style.overflow = 'hidden';
}

function cerrarModalError() {
    document.getElementById('contenedor-modal-error').classList.remove('abierto');
    document.body.style.overflow = 'auto';
}

function abrirPanelEliminar() {
    document.getElementById('contenedor-panel-eliminar').classList.add('abierto');
    document.body.style.overflow = 'hidden';
}

function cerrarPanelEliminar() {
    document.getElementById('contenedor-panel-eliminar').classList.remove('abierto');
    document.body.style.overflow = 'auto';
    
    const btnEliminar = document.getElementById('boton-confirmar-eliminar');
    if (btnEliminar) {
        btnEliminar.classList.remove('manteniendo');
        const span = btnEliminar.querySelector('span');
        if (span && btnEliminar.dataset.textoOriginal) {
            span.innerText = btnEliminar.dataset.textoOriginal;
        }
    }
}

// Lógica para mantener apretado el botón de eliminar durante 3 segundos
document.addEventListener('DOMContentLoaded', () => {
    const btnEliminar = document.getElementById('boton-confirmar-eliminar');
    if (btnEliminar) {
        let timeoutId;
        
        const startHold = (e) => {
            // Solo actuar con el click izquierdo o touch
            if (e.type === 'mousedown' && e.button !== 0) return;
            
            // Prevenir el menú contextual en móviles al mantener presionado
            if (e.type === 'touchstart') {
                e.preventDefault();
            }

            btnEliminar.classList.add('manteniendo');
            const span = btnEliminar.querySelector('span');
            if (span) {
                if (!btnEliminar.dataset.textoOriginal) {
                    btnEliminar.dataset.textoOriginal = span.innerText;
                }
                span.innerText = "Mantenga presionado...";
            }
            
            timeoutId = setTimeout(() => {
                const form = document.getElementById('formulario-eliminar');
                if (form) form.submit();
            }, 2000); // 2 segundos
        };

        const cancelHold = () => {
            btnEliminar.classList.remove('manteniendo');
            const span = btnEliminar.querySelector('span');
            if (span && btnEliminar.dataset.textoOriginal) {
                span.innerText = btnEliminar.dataset.textoOriginal;
            }
            clearTimeout(timeoutId);
        };

        // Eventos para Desktop
        btnEliminar.addEventListener('mousedown', startHold);
        btnEliminar.addEventListener('mouseup', cancelHold);
        btnEliminar.addEventListener('mouseleave', cancelHold);
        
        // Eventos para Móviles
        btnEliminar.addEventListener('touchstart', startHold, {passive: false});
        btnEliminar.addEventListener('touchend', cancelHold);
        btnEliminar.addEventListener('touchcancel', cancelHold);
    }
});