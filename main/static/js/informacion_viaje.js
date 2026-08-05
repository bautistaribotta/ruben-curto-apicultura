function abrirModalEliminarViaje() {
    document.getElementById('contenedor-panel-eliminar').classList.add('abierto');
    document.body.style.overflow = 'hidden';
}

function cerrarModalEliminarViaje() {
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

// El modal de gasto (alta, edicion y borrado) vive en gastos_viaje.js, que es
// el mismo para las tres vistas de viaje.

// Tipo de operacion elegido al abrir el modal de seleccion de cliente ('venta' | 'compra')
let tipoOperacionSeleccionada = 'venta';

// Abre el modal selector de cliente (componente compartido selector_entidad). Solo ajusta
// el titulo segun el tipo de operacion; la apertura, busqueda, teclado y foco los maneja
// el selector generico. La navegacion al elegir se engancha en el DOMContentLoaded.
function abrirModalSeleccionCliente(tipo) {
    tipoOperacionSeleccionada = tipo;

    const titulo = document.getElementById('selector-cliente-viaje-titulo');
    if (titulo) {
        titulo.textContent = tipo === 'compra'
            ? 'Seleccionar cliente para la compra'
            : 'Seleccionar cliente para la venta';
    }

    abrirSelectorEntidad('selector-cliente-viaje');
}

// Extrae el id del viaje desde la URL /informacion_viaje/<id>/
function obtenerIdViaje() {
    const coincidencia = window.location.pathname.match(/informacion_viaje\/(\d+)/);
    return coincidencia ? coincidencia[1] : '';
}

document.addEventListener('DOMContentLoaded', () => {
    const btnEliminar = document.getElementById('boton-confirmar-eliminar');
    if (btnEliminar) {
        let timeoutId;
        
        const startHold = (e) => {
            if (e.type === 'mousedown' && e.button !== 0) return;
            if (e.type === 'touchstart') e.preventDefault();

            btnEliminar.classList.add('manteniendo');
            const span = btnEliminar.querySelector('span');
            if (span) {
                if (!btnEliminar.dataset.textoOriginal) {
                    btnEliminar.dataset.textoOriginal = span.innerText;
                }
                span.innerText = "Mantenga presionado...";
            }
            
            timeoutId = setTimeout(() => {
                document.getElementById('formulario-eliminar').submit();
            }, 2000); // 2 segundos
        };

        const stopHold = () => {
            clearTimeout(timeoutId);
            btnEliminar.classList.remove('manteniendo');
            const span = btnEliminar.querySelector('span');
            if (span && btnEliminar.dataset.textoOriginal) {
                span.innerText = btnEliminar.dataset.textoOriginal;
            }
        };

        btnEliminar.addEventListener('mousedown', startHold);
        btnEliminar.addEventListener('touchstart', startHold, {passive: false});
        btnEliminar.addEventListener('mouseup', stopHold);
        btnEliminar.addEventListener('mouseleave', stopHold);
        btnEliminar.addEventListener('touchend', stopHold);
        btnEliminar.addEventListener('touchcancel', stopHold);
    }

    // Lógica para añadir y quitar dinámicamente múltiples destinos en el slide-over
    const btnAgregarDestino = document.getElementById('btn-agregar-destino');
    const btnQuitarDestino = document.getElementById('btn-quitar-destino');
    const contenedorDestinos = document.getElementById('contenedor-destinos');

    if (btnAgregarDestino && btnQuitarDestino && contenedorDestinos) {
        const contenedorBotones = btnAgregarDestino.parentElement;

        // Evento Agregar
        btnAgregarDestino.addEventListener('click', () => {
            const nuevoInput = document.createElement('input');
            nuevoInput.type = 'text';
            nuevoInput.name = 'destino';
            nuevoInput.placeholder = 'Siguiente destino...';
            nuevoInput.required = true;
            nuevoInput.maxLength = 30;
            nuevoInput.pattern = '[a-zA-ZÁÉÍÓÚáéíóúñÑ\\s\\d]{3,}';
            nuevoInput.style.marginTop = '0.5rem';

            // Insertamos el nuevo input antes de los botones
            contenedorDestinos.insertBefore(nuevoInput, contenedorBotones);
            inicializarAutocompletadoCiudad(nuevoInput);

            // Mostrar el botón de quitar porque ahora hay más de un input
            btnQuitarDestino.style.display = 'flex';
        });

        // Evento Quitar
        btnQuitarDestino.addEventListener('click', () => {
            const inputs = contenedorDestinos.querySelectorAll('input[name="destino"]');
            
            if (inputs.length > 1) {
                // Elimina el último input y su lista de sugerencias asociada
                const ultimoInput = inputs[inputs.length - 1];
                const listaSugerencias = ultimoInput.nextElementSibling;
                if (listaSugerencias && listaSugerencias.classList.contains('lista-autocompletado-ciudades')) {
                    listaSugerencias.remove();
                }
                contenedorDestinos.removeChild(ultimoInput);
            }

            // Si después de eliminar queda solo 1, oculto el botón "Quitar"
            if (inputs.length - 1 <= 1) {
                btnQuitarDestino.style.display = 'none';
            }
        });

        // Si el viaje ya trae varios destinos cargados, muestro el botón "Quitar"
        if (contenedorDestinos.querySelectorAll('input[name="destino"]').length > 1) {
            btnQuitarDestino.style.display = 'flex';
        }
    }

    // El selector de cliente (componente compartido) avisa la eleccion por evento;
    // navego a la nueva operacion (compra o venta segun el tipo) del cliente elegido,
    // dentro de este viaje.
    const modalCliente = document.getElementById('selector-cliente-viaje');
    if (modalCliente) {
        modalCliente.addEventListener('selector-entidad:elegir', (evento) => {
            const idCliente = evento.detail.id;
            const idViaje = obtenerIdViaje();
            const base = tipoOperacionSeleccionada === 'compra' ? 'nueva_operacion_compra' : 'nueva_operacion_venta';
            window.location.href = `/${base}/${idCliente}/?viaje=${idViaje}`;
        });
    }
});