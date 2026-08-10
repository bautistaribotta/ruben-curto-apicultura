// Alta, edicion y borrado de los gastos de un viaje.
//
// Las tres vistas de viaje (miel/cera, cereal y reparto) comparten el mismo
// markup: el panel #panel-gasto dentro de #formulario-gasto, y la lista de
// filas que arma el partial gastos_viaje.html. Lo unico propio de cada vista
// son los nombres de las acciones del POST, que llegan en data-* del form.
//
// Un solo modal para todo: tocar una fila lo abre en modo edicion y el boton
// "Anadir gasto" lo abre vacio. Para eliminar no hay un segundo modal: el
// boton del pie se mantiene apretado tres segundos, igual que el borrado de un
// viaje.

(() => {
    const formulario = document.getElementById('formulario-gasto');
    if (!formulario) return;

    const contenedor = document.getElementById('contenedor-modal-gasto');
    const campoAccion = document.getElementById('gasto-accion');
    const campoId = document.getElementById('gasto-id');
    const campoTipo = document.getElementById('tipo-gasto');
    const campoMonto = document.getElementById('monto-gasto');
    const titulo = document.getElementById('gasto-titulo');
    const bajada = document.getElementById('gasto-bajada');
    const botonGuardar = document.getElementById('gasto-guardar');
    // Campos que solo se piden cuando el gasto es de combustible.
    const bloqueCombustible = document.getElementById('gasto-combustible');
    const campoEstacion = document.getElementById('gasto-estacion');
    const campoLitros = document.getElementById('gasto-litros');
    const campoPagada = document.getElementById('gasto-pagada');
    const zonaBorrar = document.getElementById('gasto-zona-borrar');
    const botonEliminar = document.getElementById('gasto-borrar');
    const etiquetaEliminar = document.getElementById('gasto-borrar-texto');
    const textoEliminar = etiquetaEliminar.textContent;

    // La bajada de alta la escribe cada vista con su propio calculo (caja,
    // subtotal, ganancia), asi que me la guardo para poder volver a ponerla.
    const bajadaAlta = bajada.textContent;

    // 'nuevo' | 'editar'. El boton de eliminar solo aparece al editar: un gasto
    // que todavia no existe no se puede borrar.
    function aplicarModo(modo) {
        zonaBorrar.hidden = modo !== 'editar';
        soltarBorrado();
    }

    function mostrar() {
        contenedor.classList.add('abierto');
        document.body.style.overflow = 'hidden';
        campoTipo.focus();
    }

    // El bloque de combustible (estacion, litros, pagada) solo se muestra cuando el
    // tipo elegido es Combustible. Al ocultarlo no se limpia: el servidor ignora esos
    // datos si el gasto no es de combustible.
    function aplicarCombustible() {
        if (bloqueCombustible) bloqueCombustible.hidden = campoTipo.value !== 'Combustible';
    }

    function abrirModalGasto() {
        formulario.reset();
        campoAccion.value = formulario.dataset.accionNuevo;
        campoId.value = '';
        titulo.textContent = 'Registrar gasto';
        bajada.textContent = bajadaAlta;
        botonGuardar.textContent = 'Guardar';
        aplicarModo('nuevo');
        aplicarCombustible();
        mostrar();
    }

    function abrirGastoEdicion(datos) {
        formulario.reset();
        campoAccion.value = formulario.dataset.accionEditar;
        campoId.value = datos.gasto;
        titulo.textContent = 'Editar gasto';
        bajada.textContent = 'Corregí el tipo o el monto. La fecha queda la del día en que se cargó.';
        botonGuardar.textContent = 'Guardar cambios';
        campoTipo.value = datos.tipo;
        ponerValorMiles(campoMonto, datos.monto);
        // Precargo los datos de la carga si el gasto es de combustible. Los litros
        // vienen con punto decimal desde el modelo; los muestro con coma como se cargan.
        if (campoEstacion) campoEstacion.value = datos.estacion || '';
        if (campoLitros) campoLitros.value = datos.litros ? datos.litros.replace('.', ',') : '';
        if (campoPagada) campoPagada.checked = datos.pagada === '1';
        aplicarModo('editar');
        aplicarCombustible();
        mostrar();
    }

    function cerrarModalGasto() {
        contenedor.classList.remove('abierto');
        document.body.style.overflow = 'auto';
        formulario.reset();
        campoAccion.value = formulario.dataset.accionNuevo;
        campoId.value = '';
        aplicarModo('nuevo');
    }

    // Los templates abren y cierran el modal desde onclick, asi que las dos
    // funciones tienen que quedar colgadas del window.
    window.abrirModalGasto = abrirModalGasto;
    window.cerrarModalGasto = cerrarModalGasto;

    // Al cambiar el tipo, muestro u oculto el bloque de combustible.
    campoTipo.addEventListener('change', aplicarCombustible);

    // Las filas comparten marcado y se rearman en cada carga, asi que van por
    // delegacion. El data-gasto deja afuera las filas del reparto que parecen
    // gastos pero son campos del viaje: esas llevan su propio onclick.
    document.addEventListener('click', (evento) => {
        const fila = evento.target.closest('.vd-gasto--editable[data-gasto]');
        if (fila) {
            abrirGastoEdicion(fila.dataset);
        }
    });

    // El boton de eliminar hay que mantenerlo apretado tres segundos, como el
    // borrado de un viaje: el gasto no vuelve, asi que el gesto tiene que
    // costar mas que un click de paso. Soltar antes cancela.
    let cuentaRegresiva;

    function arrancarBorrado(evento) {
        if (evento.type === 'mousedown' && evento.button !== 0) return;
        // En el celular, mantener apretado abre el menu del navegador si no lo freno
        if (evento.type === 'touchstart') evento.preventDefault();

        botonEliminar.classList.add('manteniendo');
        etiquetaEliminar.textContent = 'Mantené apretado...';

        cuentaRegresiva = setTimeout(() => {
            campoAccion.value = formulario.dataset.accionEliminar;
            // submit() y no requestSubmit(): el tipo y el monto siguen siendo
            // required, asi que hay que saltear la validacion del navegador, que
            // al borrar no tiene por que exigirlos.
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
            cerrarModalGasto();
        }
    });

    // Despues de guardar, la vista vuelve con ?gasto=<id>. Traigo esa fila a la
    // vista y la resalto un momento: la lista de gastos scrollea y sin esto el
    // usuario ve el cartel de exito pero no ve cual cambio.
    const idMarcado = new URLSearchParams(window.location.search).get('gasto');
    if (idMarcado) {
        const fila = document.getElementById(`gasto-${idMarcado}`);
        if (fila) {
            const quieto = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
            fila.scrollIntoView({block: 'nearest', behavior: quieto ? 'auto' : 'smooth'});
            fila.classList.add('vd-gasto--recien');
            fila.addEventListener('animationend', () => fila.classList.remove('vd-gasto--recien'), {once: true});
        }

        // Saco la marca de la URL para que recargar no vuelva a resaltar la fila
        const url = new URL(window.location.href);
        url.searchParams.delete('gasto');
        window.history.replaceState({}, '', url);
    }
})();
