// Alta, edicion y borrado de los gastos de un viaje.
//
// Las tres vistas de viaje (miel/cera, cereal y reparto) comparten el mismo
// markup: el panel #panel-gasto dentro de #formulario-gasto, y la lista de
// filas que arma el partial gastos_viaje.html. Lo unico propio de cada vista
// son los nombres de las acciones del POST, que llegan en data-* del form.
//
// Un solo modal para las tres cosas: tocar una fila lo abre en modo edicion,
// el boton "Anadir gasto" lo abre vacio, y eliminar es un paso mas adentro del
// mismo panel en vez de un segundo modal encima.

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
    const zonaBorrar = document.getElementById('gasto-zona-borrar');
    const confirmacion = document.getElementById('gasto-confirmar');
    const resumen = document.getElementById('gasto-confirmar-resumen');
    const campos = document.getElementById('gasto-campos');
    const acciones = document.getElementById('gasto-acciones');
    const botonEliminar = document.getElementById('gasto-confirmar-si');
    const etiquetaEliminar = botonEliminar.querySelector('span');
    const textoEliminar = etiquetaEliminar.textContent;

    // La bajada de alta la escribe cada vista con su propio calculo (caja,
    // subtotal, ganancia), asi que me la guardo para poder volver a ponerla.
    const bajadaAlta = bajada.textContent;

    // 'nuevo' | 'editar' | 'confirmar'. En 'confirmar' el cuerpo del panel se
    // esconde y queda solo la pregunta: el modal sigue siendo el mismo gasto.
    function aplicarModo(modo) {
        const confirmando = modo === 'confirmar';
        campos.hidden = confirmando;
        acciones.hidden = confirmando;
        zonaBorrar.hidden = modo !== 'editar';
        confirmacion.hidden = !confirmando;
        soltarBorrado();
    }

    function mostrar() {
        contenedor.classList.add('abierto');
        document.body.style.overflow = 'hidden';
        campoTipo.focus();
    }

    function abrirModalGasto() {
        formulario.reset();
        campoAccion.value = formulario.dataset.accionNuevo;
        campoId.value = '';
        titulo.textContent = 'Registrar gasto';
        bajada.textContent = bajadaAlta;
        botonGuardar.textContent = 'Guardar';
        aplicarModo('nuevo');
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
        resumen.textContent = datos.resumen;
        aplicarModo('editar');
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

    // Las filas comparten marcado y se rearman en cada carga, asi que van por
    // delegacion. El data-gasto deja afuera las filas del reparto que parecen
    // gastos pero son campos del viaje: esas llevan su propio onclick.
    document.addEventListener('click', (evento) => {
        const fila = evento.target.closest('.vd-gasto--editable[data-gasto]');
        if (fila) {
            abrirGastoEdicion(fila.dataset);
        }
    });

    document.getElementById('gasto-borrar').addEventListener('click', () => aplicarModo('confirmar'));
    document.getElementById('gasto-confirmar-no').addEventListener('click', () => aplicarModo('editar'));

    // El "Si, eliminar" hay que mantenerlo apretado tres segundos, como el
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
            // required y estan escondidos, asi que hay que saltear la validacion
            // del navegador, que no puede pedir un campo que no se ve.
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
