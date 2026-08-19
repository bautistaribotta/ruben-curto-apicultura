// Devolucion del sobrante de la caja de un viaje de miel/cera.
//
// Cuando la caja cierra con sobrante, el chofer tiene esa plata. Este modal
// registra que hizo con ella: la devolvio toda (no queda nada pendiente) o
// devolvio una parte y se quedo con el resto. Lo que retuvo se calcula en vivo
// (sobrante - devuelto) y se muestra como el pago que se le cargara al empleado.
//
// Un solo modal para alta y edicion: el estado actual viaja en los data-* del
// formulario y al abrir se preselecciona. Quitar la devolucion usa el mismo gesto
// de mantener apretado que el gasto y el ingreso.

(() => {
    const formulario = document.getElementById('formulario-devolucion');
    if (!formulario) return;

    const contenedor = document.getElementById('contenedor-modal-devolucion');
    const campoEstado = document.getElementById('devol-estado');
    const opciones = Array.from(formulario.querySelectorAll('.devol-opcion'));
    const montoCampo = document.getElementById('devol-monto-campo');
    const campoMonto = document.getElementById('monto-devuelto');
    const hint = document.getElementById('devol-hint');
    const botonGuardar = document.getElementById('devolucion-guardar');
    const zonaBorrar = document.getElementById('devolucion-zona-borrar');
    const botonEliminar = document.getElementById('devolucion-borrar');
    const etiquetaEliminar = document.getElementById('devolucion-borrar-texto');
    const textoEliminar = etiquetaEliminar.textContent;

    const sobrante = parseInt(formulario.dataset.sobrante || '0', 10) || 0;
    const empleado = formulario.dataset.empleado || 'el chofer';
    const formateador = new Intl.NumberFormat('es-AR');

    let seleccion = '';

    function soloDigitos(texto) {
        return (texto || '').replace(/\D/g, '');
    }

    // Recalcula el estado del modal segun la opcion elegida: habilita Guardar y,
    // en la parcial, muestra el pago que se generara o el error si lo devuelto no
    // es menor al sobrante.
    function actualizar() {
        if (seleccion === 'total') {
            botonGuardar.disabled = false;
            return;
        }
        if (seleccion === 'parcial') {
            const crudo = soloDigitos(campoMonto.value);
            if (crudo === '') {
                hint.textContent = 'El resto queda como pago del empleado.';
                hint.classList.remove('devol-hint--error', 'devol-hint--ok');
                botonGuardar.disabled = true;
                return;
            }
            const devuelto = parseInt(crudo, 10);
            if (devuelto >= sobrante) {
                hint.textContent = 'Tiene que ser menor al sobrante. Si devolvió todo, elegí "Devolvió todo".';
                hint.classList.add('devol-hint--error');
                hint.classList.remove('devol-hint--ok');
                botonGuardar.disabled = true;
                return;
            }
            const retenido = sobrante - devuelto;
            hint.textContent = `Se registrará un pago de $${formateador.format(retenido)} a ${empleado}.`;
            hint.classList.add('devol-hint--ok');
            hint.classList.remove('devol-hint--error');
            botonGuardar.disabled = false;
            return;
        }
        botonGuardar.disabled = true;
    }

    function seleccionar(opcion) {
        seleccion = opcion;
        campoEstado.value = opcion;

        opciones.forEach((boton) => {
            const activa = boton.dataset.opcion === opcion;
            boton.classList.toggle('is-sel', activa);
            boton.setAttribute('aria-checked', activa ? 'true' : 'false');
        });

        const esParcial = opcion === 'parcial';
        montoCampo.hidden = !esParcial;
        // Deshabilitar el campo cuando no es parcial lo saca del POST y de la
        // validacion del navegador; habilitarlo lo vuelve requerido.
        campoMonto.disabled = !esParcial;
        campoMonto.required = esParcial;
        if (esParcial) campoMonto.focus();

        actualizar();
    }

    function mostrar() {
        contenedor.classList.add('abierto');
        document.body.style.overflow = 'hidden';
    }

    function abrirModalDevolucion() {
        const estadoActual = formulario.dataset.estado || '';
        const registrada = estadoActual === 'total' || estadoActual === 'parcial';

        // Arranco limpio y despues aplico el estado guardado, si lo hay.
        seleccion = '';
        campoEstado.value = '';
        campoMonto.value = '';
        opciones.forEach((boton) => {
            boton.classList.remove('is-sel');
            boton.setAttribute('aria-checked', 'false');
        });
        montoCampo.hidden = true;
        campoMonto.disabled = true;
        campoMonto.required = false;
        botonGuardar.disabled = true;
        hint.classList.remove('devol-hint--error', 'devol-hint--ok');
        hint.textContent = 'El resto queda como pago del empleado.';

        if (registrada) {
            seleccionar(estadoActual);
            if (estadoActual === 'parcial') {
                ponerValorMiles(campoMonto, formulario.dataset.devuelto || '');
                actualizar();
            }
        }

        // Quitar solo tiene sentido si ya hay una devolucion cargada.
        zonaBorrar.hidden = !registrada;
        soltarBorrado();

        mostrar();
    }

    function cerrarModalDevolucion() {
        contenedor.classList.remove('abierto');
        document.body.style.overflow = 'auto';
        soltarBorrado();
    }

    window.abrirModalDevolucion = abrirModalDevolucion;
    window.cerrarModalDevolucion = cerrarModalDevolucion;

    opciones.forEach((boton) => {
        boton.addEventListener('click', () => seleccionar(boton.dataset.opcion));
    });

    campoMonto.addEventListener('input', actualizar);

    // Quitar la devolucion: se mantiene apretado tres segundos, igual que el
    // borrado de un gasto o un ingreso. Manda estado vacio para volver a "sin
    // registrar". submit() y no requestSubmit() para saltear la validacion del
    // monto, que al quitar no corresponde exigir.
    let cuentaRegresiva;

    function arrancarBorrado(evento) {
        if (evento.type === 'mousedown' && evento.button !== 0) return;
        if (evento.type === 'touchstart') evento.preventDefault();

        botonEliminar.classList.add('manteniendo');
        etiquetaEliminar.textContent = 'Mantené apretado...';

        cuentaRegresiva = setTimeout(() => {
            campoEstado.value = '';
            campoMonto.disabled = true;
            campoMonto.required = false;
            formulario.submit();
        }, 3000);
    }

    function soltarBorrado() {
        clearTimeout(cuentaRegresiva);
        botonEliminar.classList.remove('manteniendo');
        etiquetaEliminar.textContent = textoEliminar;
    }

    botonEliminar.addEventListener('mousedown', arrancarBorrado);
    botonEliminar.addEventListener('mouseup', soltarBorrado);
    botonEliminar.addEventListener('mouseleave', soltarBorrado);
    botonEliminar.addEventListener('touchstart', arrancarBorrado, {passive: false});
    botonEliminar.addEventListener('touchend', soltarBorrado);
    botonEliminar.addEventListener('touchcancel', soltarBorrado);

    document.addEventListener('keydown', (evento) => {
        if (evento.key === 'Escape' && contenedor.classList.contains('abierto')) {
            cerrarModalDevolucion();
        }
    });
})();
