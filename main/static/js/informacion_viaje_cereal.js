// Logica propia de la vista "Informacion del viaje de cereal".
// La eliminacion del viaje reutiliza abrirPanelEliminar()/cerrarPanelEliminar()
// de paneles.js (mismo markup #contenedor-panel-eliminar / #boton-confirmar-eliminar),
// y el modal de gastos vive en gastos_viaje.js, compartido con los otros viajes.

document.addEventListener('DOMContentLoaded', () => {
    // Logica para anadir y quitar dinamicamente multiples destinos en el slide-over de edicion
    const btnAgregarDestino = document.getElementById('btn-agregar-destino-cereal');
    const btnQuitarDestino = document.getElementById('btn-quitar-destino-cereal');
    const contenedorDestinos = document.getElementById('contenedor-destinos-cereal');

    if (btnAgregarDestino && btnQuitarDestino && contenedorDestinos) {
        const contenedorBotones = btnAgregarDestino.parentElement;

        btnAgregarDestino.addEventListener('click', () => {
            const nuevoInput = document.createElement('input');
            nuevoInput.type = 'text';
            nuevoInput.name = 'destino';
            nuevoInput.placeholder = 'Siguiente destino...';
            nuevoInput.required = true;
            nuevoInput.maxLength = 30;
            nuevoInput.pattern = '[a-zA-ZÁÉÍÓÚáéíóúñÑ\\s\\d]{3,}';
            nuevoInput.style.marginTop = '0.5rem';

            contenedorDestinos.insertBefore(nuevoInput, contenedorBotones);
            inicializarAutocompletadoCiudad(nuevoInput);

            btnQuitarDestino.style.display = 'flex';
        });

        btnQuitarDestino.addEventListener('click', () => {
            const inputs = contenedorDestinos.querySelectorAll('input[name="destino"]');

            if (inputs.length > 1) {
                const ultimoInput = inputs[inputs.length - 1];
                const listaSugerencias = ultimoInput.nextElementSibling;
                if (listaSugerencias && listaSugerencias.classList.contains('lista-autocompletado-ciudades')) {
                    listaSugerencias.remove();
                }
                contenedorDestinos.removeChild(ultimoInput);
            }

            if (inputs.length - 1 <= 1) {
                btnQuitarDestino.style.display = 'none';
            }
        });

        // Si el viaje ya trae varios destinos cargados, muestro el boton "Quitar"
        if (contenedorDestinos.querySelectorAll('input[name="destino"]').length > 1) {
            btnQuitarDestino.style.display = 'flex';
        }
    }

    // Dadora de carga: el markup ya llega con el estado correcto desde la vista;
    // esto solo engancha el switch y la forma de cobro para las ediciones en vivo.
    inicializarDadoraCarga({
        toggle: 'dadora-toggle-cereal',
        campos: 'dadora-campos-cereal',
        nombre: 'dadora-nombre-cereal',
        tipo: 'dadora-tipo-cereal',
        valores: {
            porcentaje: { grupo: 'dadora-pct-grupo-cereal', input: 'dadora-pct-cereal' },
            tonelada: { grupo: 'dadora-ton-grupo-cereal', input: 'dadora-ton-cereal' },
            efectivo: { grupo: 'dadora-efe-grupo-cereal', input: 'dadora-efe-cereal' },
        },
    });
});
