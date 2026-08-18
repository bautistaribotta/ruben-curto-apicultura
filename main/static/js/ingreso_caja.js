// Alta, edicion y borrado del dinero que entra a la caja del viaje.
//
// Es el hermano simple de gastos_viaje.js: solo miel/cera tiene caja, y un
// ingreso no tiene tipo ni carga de combustible, solo un monto. El concepto
// (transferencia al chofer) es fijo, asi que no viaja ningun campo mas.
//
// Un solo modal para todo: el boton "Anadir dinero" lo abre vacio y tocar una
// fila de transferencia lo abre en modo edicion. Para eliminar no hay un segundo
// modal: el boton del pie se mantiene apretado tres segundos, igual que el gasto.

(() => {
    const formulario = document.getElementById('formulario-ingreso');
    if (!formulario) return;

    const contenedor = document.getElementById('contenedor-modal-ingreso');
    const campoAccion = document.getElementById('ingreso-accion');
    const campoId = document.getElementById('ingreso-id');
    const campoMonto = document.getElementById('monto-ingreso');
    const titulo = document.getElementById('ingreso-titulo');
    const bajada = document.getElementById('ingreso-bajada');
    const botonGuardar = document.getElementById('ingreso-guardar');
    const zonaBorrar = document.getElementById('ingreso-zona-borrar');
    const botonEliminar = document.getElementById('ingreso-borrar');
    const etiquetaEliminar = document.getElementById('ingreso-borrar-texto');
    const textoEliminar = etiquetaEliminar.textContent;

    // Me guardo el titulo y la bajada del alta para poder volver a ponerlos
    // cuando el modal pasa de editar a cargar uno nuevo.
    const tituloAlta = titulo.textContent;
    const bajadaAlta = bajada.textContent;

    // El boton de eliminar solo aparece al editar: un ingreso que todavia no
    // existe no se puede borrar.
    function aplicarModo(modo) {
        zonaBorrar.hidden = modo !== 'editar';
        soltarBorrado();
    }

    function mostrar() {
        contenedor.classList.add('abierto');
        document.body.style.overflow = 'hidden';
        campoMonto.focus();
    }

    function abrirModalIngreso() {
        formulario.reset();
        campoAccion.value = 'nuevo_ingreso';
        campoId.value = '';
        titulo.textContent = tituloAlta;
        bajada.textContent = bajadaAlta;
        botonGuardar.textContent = 'Guardar';
        aplicarModo('nuevo');
        mostrar();
    }

    function abrirIngresoEdicion(datos) {
        formulario.reset();
        campoAccion.value = 'editar_ingreso';
        campoId.value = datos.ingreso;
        titulo.textContent = 'Editar transferencia';
        bajada.textContent = 'Corregí el monto transferido al chofer. La fecha queda la del día en que se cargó.';
        botonGuardar.textContent = 'Guardar cambios';
        ponerValorMiles(campoMonto, datos.monto);
        aplicarModo('editar');
        mostrar();
    }

    function cerrarModalIngreso() {
        contenedor.classList.remove('abierto');
        document.body.style.overflow = 'auto';
        formulario.reset();
        campoAccion.value = 'nuevo_ingreso';
        campoId.value = '';
        aplicarModo('nuevo');
    }

    // Los templates abren y cierran el modal desde onclick, asi que las dos
    // funciones tienen que quedar colgadas del window.
    window.abrirModalIngreso = abrirModalIngreso;
    window.cerrarModalIngreso = cerrarModalIngreso;

    // Las filas de transferencia se rearman en cada carga, asi que van por
    // delegacion. El data-ingreso las distingue de los gastos y las operaciones.
    document.addEventListener('click', (evento) => {
        const fila = evento.target.closest('.vd-gasto--editable[data-ingreso]');
        if (fila) {
            abrirIngresoEdicion(fila.dataset);
        }
    });

    // El boton de eliminar hay que mantenerlo apretado tres segundos, como el
    // borrado de un gasto: el ingreso no vuelve, asi que el gesto tiene que
    // costar mas que un click de paso. Soltar antes cancela.
    let cuentaRegresiva;

    function arrancarBorrado(evento) {
        if (evento.type === 'mousedown' && evento.button !== 0) return;
        // En el celular, mantener apretado abre el menu del navegador si no lo freno
        if (evento.type === 'touchstart') evento.preventDefault();

        botonEliminar.classList.add('manteniendo');
        etiquetaEliminar.textContent = 'Mantené apretado...';

        cuentaRegresiva = setTimeout(() => {
            campoAccion.value = 'eliminar_ingreso';
            // submit() y no requestSubmit(): el monto sigue siendo required, asi
            // que hay que saltear la validacion del navegador, que al borrar no
            // tiene por que exigirlo.
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
            cerrarModalIngreso();
        }
    });

    // Despues de guardar, la vista vuelve con ?ingreso=<id>. Traigo esa fila a la
    // vista y la resalto un momento, igual que con los gastos.
    const idMarcado = new URLSearchParams(window.location.search).get('ingreso');
    if (idMarcado) {
        const fila = document.getElementById(`ingreso-${idMarcado}`);
        if (fila) {
            const quieto = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
            fila.scrollIntoView({block: 'nearest', behavior: quieto ? 'auto' : 'smooth'});
            fila.classList.add('vd-gasto--recien');
            fila.addEventListener('animationend', () => fila.classList.remove('vd-gasto--recien'), {once: true});
        }

        // Saco la marca de la URL para que recargar no vuelva a resaltar la fila
        const url = new URL(window.location.href);
        url.searchParams.delete('ingreso');
        window.history.replaceState({}, '', url);
    }
})();
