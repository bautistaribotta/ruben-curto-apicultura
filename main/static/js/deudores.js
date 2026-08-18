document.addEventListener('DOMContentLoaded', () => {
    // Selecciono los elementos del DOM que voy a usar para la búsqueda
    const contenedorTabla = document.getElementById('tabla-deudores-container');
    const chipsTipo = document.querySelectorAll('#chips-tipo .prod-chip');
    const optsValuacion = document.querySelectorAll('#deu-valuacion .deu-seg__opt');

    // --- Filtros por cliente y por producto (chip + modal selector) ---
    // Cada chip guarda el estado APLICADO (id + nombre) en los data-filtro-* de su
    // contenedor; es la fuente de verdad que lee buscar(). Los chips viven fuera de la
    // region que el AJAX reemplaza, asi que su dataset sobrevive a los refrescos.
    const clienteCont = document.getElementById('deu-cliente');
    const productoCont = document.getElementById('deu-producto');
    const modalCliente = document.getElementById('selector-cliente-deuda');
    const modalProducto = document.getElementById('selector-producto-deuda');

    // Base de valuacion elegida en el segmentado ('hoy' u 'origen'). Solo cambia las
    // tarjetas de resumen; la tabla muestra ambas columnas siempre.
    const valuacionActiva = () => {
        const activo = document.querySelector('#deu-valuacion .deu-seg__opt.is-active');
        return activo ? activo.dataset.valuacion : 'hoy';
    };

    // --- Filtro por fecha (componente compartido #filtro-fechas) ---
    // filtro_fechas.js administra el popover y guarda el estado aplicado (desde/
    // hasta en ISO) en los data-* del contenedor, que es lo unico que lee buscar().
    const fechas = document.getElementById('filtro-fechas');

    // Devuelve el tipo filtrado (cobros/pagos) o '' si no hay ninguno activo (= todas)
    const tipoActivo = () => {
        const activo = document.querySelector('#chips-tipo .prod-chip.is-active');
        return activo ? activo.dataset.tipo : '';
    };

    /**
     * Función para realizar las búsquedas de deudores mediante AJAX.
     * @param {string|null} urlString - URL opcional para la paginación.
     */
    const buscar = (urlString = null) => {
        if (!contenedorTabla) return;

        let url;

        if (urlString) {
            url = new URL(urlString, window.location.origin);
            // Paginacion: el link ya trae los filtros server-side, pero refuerzo el
            // rango de fechas desde el estado del chip (la fuente de verdad) para que
            // sobreviva a "Anterior"/"Siguiente" aunque el link llegara sin ellos
            // (por ej. una plantilla vieja cacheada). El chip vive fuera de la region
            // que el AJAX reemplaza, asi que su dataset sigue reflejando lo aplicado.
            const dd = fechas ? fechas.dataset.desde : '';
            const hh = fechas ? fechas.dataset.hasta : '';
            if (dd) {
                url.searchParams.set('desde', dd);
            } else {
                url.searchParams.delete('desde');
            }
            if (hh) {
                url.searchParams.set('hasta', hh);
            } else {
                url.searchParams.delete('hasta');
            }
            // Mismo refuerzo para cliente y producto: los chips viven fuera de la region
            // que reemplaza el AJAX, asi que su dataset sigue siendo la fuente de verdad.
            const cid = clienteCont ? clienteCont.dataset.filtroId : '';
            if (cid) {
                url.searchParams.set('cliente', cid);
            } else {
                url.searchParams.delete('cliente');
            }
            const pid = productoCont ? productoCont.dataset.filtroId : '';
            if (pid) {
                url.searchParams.set('producto', pid);
            } else {
                url.searchParams.delete('producto');
            }
            // Mismo refuerzo para la valuacion: el segmentado vive fuera de la region
            // que reemplaza el AJAX, asi que su estado sigue siendo la fuente de verdad.
            url.searchParams.set('valuacion', valuacionActiva());
        } else {
            url = new URL(window.location.href);
            // Cliente y producto elegidos: los tomo del estado de sus chips.
            const clienteId = clienteCont ? clienteCont.dataset.filtroId : '';
            if (clienteId) {
                url.searchParams.set('cliente', clienteId);
            } else {
                url.searchParams.delete('cliente');
            }
            const productoId = productoCont ? productoCont.dataset.filtroId : '';
            if (productoId) {
                url.searchParams.set('producto', productoId);
            } else {
                url.searchParams.delete('producto');
            }
            const tipo = tipoActivo();
            if (tipo) {
                url.searchParams.set('tipo', tipo);
            } else {
                url.searchParams.delete('tipo');
            }
            // Fechas aplicadas: las tomo del estado del contenedor, no de los inputs
            const dd = fechas ? fechas.dataset.desde : '';
            const hh = fechas ? fechas.dataset.hasta : '';
            if (dd) {
                url.searchParams.set('desde', dd);
            } else {
                url.searchParams.delete('desde');
            }
            if (hh) {
                url.searchParams.set('hasta', hh);
            } else {
                url.searchParams.delete('hasta');
            }
            url.searchParams.set('valuacion', valuacionActiva());
            url.searchParams.delete('page');
        }

        // Realizo la petición fetch indicando que es XMLHttpRequest
        fetch(url, {
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
            },
        })
        .then((response) => response.text())
        .then((html) => {
            // La respuesta trae dos regiones (tarjetas y tabla). Las parseo y reemplazo
            // cada una por su id, sin tocar la barra de busqueda/filtros.
            const fragmento = document.createElement('div');
            fragmento.innerHTML = html;

            const nuevasTarjetas = fragmento.querySelector('#deu-stats-region');
            const nuevaTabla = fragmento.querySelector('#tabla-deudores-region');
            const nuevaListaCliente = fragmento.querySelector('#deu-selector-clientes-region');
            const nuevaListaProducto = fragmento.querySelector('#deu-selector-productos-region');

            const tarjetas = document.getElementById('deu-stats-region');
            if (nuevasTarjetas && tarjetas) {
                tarjetas.innerHTML = nuevasTarjetas.innerHTML;
            }
            if (nuevaTabla && contenedorTabla) {
                contenedorTabla.innerHTML = nuevaTabla.innerHTML;
            }
            // Las listas de los modales siguen al filtro de tipo/fechas: reemplazo solo
            // los <li> (el shell de cada modal y sus listeners quedan intactos).
            const listaCliente = modalCliente ? modalCliente.querySelector('.selent__lista') : null;
            if (nuevaListaCliente && listaCliente) {
                listaCliente.innerHTML = nuevaListaCliente.innerHTML;
            }
            const listaProducto = modalProducto ? modalProducto.querySelector('.selent__lista') : null;
            if (nuevaListaProducto && listaProducto) {
                listaProducto.innerHTML = nuevaListaProducto.innerHTML;
            }

            // Actualizo la URL en la barra del navegador sin recargar la página
            window.history.pushState({}, '', url);

            // Vuelvo a vincular los eventos a los nuevos botones de paginación
            vincularPaginacion();
        })
        .catch((error) => console.error('Error en la búsqueda:', error));
    };

    /**
     * Función para atrapar los clicks en los botones de paginación
     * y evitar que recarguen la página entera, usando AJAX en su lugar.
     */
    const vincularPaginacion = () => {
        if (!contenedorTabla) return;
        const linksPaginacion = contenedorTabla.querySelectorAll('.paginacion-botones a');

        linksPaginacion.forEach((link) => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                buscar(link.href);
            });
        });
    };

    // ---------------------------------------------------------------------------
    // Chips de filtro por entidad (cliente y producto). Cada chip abre su modal; el
    // modal avisa la eleccion por evento y aca aplico el filtro. La "x" del chip limpia.
    // Misma mecanica para ambos, parametrizada por prefijo de clase y etiqueta vacia.
    // ---------------------------------------------------------------------------
    const configurarChipFiltro = (cont, modal, { prefijo, etiquetaVacia, ariaLimpiar }) => {
        if (!cont || !modal) return;
        const trigger = cont.querySelector(`.${prefijo}__trigger`);
        const label = cont.querySelector(`.${prefijo}__label`);
        if (!trigger || !label) return;
        const claseClear = `${prefijo}__clear`;

        // Crea o quita la "x" para limpiar dentro del chip segun haya filtro elegido.
        const actualizarClear = (activo) => {
            let clearEl = trigger.querySelector(`.${claseClear}`);
            if (activo && !clearEl) {
                clearEl = document.createElement('span');
                clearEl.className = `material-symbols-outlined ${claseClear}`;
                clearEl.setAttribute('role', 'button');
                clearEl.setAttribute('tabindex', '0');
                clearEl.setAttribute('aria-label', ariaLimpiar);
                clearEl.textContent = 'close';
                trigger.appendChild(clearEl);
            } else if (!activo && clearEl) {
                clearEl.remove();
            }
        };

        // Vuelca el estado elegido al chip (label, activo, boton limpiar) y al data-*.
        const setEstado = (id, nombre) => {
            cont.dataset.filtroId = id || '';
            cont.dataset.filtroNombre = nombre || '';
            const activo = Boolean(id);
            label.textContent = activo ? nombre : etiquetaVacia;
            trigger.classList.toggle('is-active', activo);
            actualizarClear(activo);
        };

        const limpiar = () => {
            setEstado('', '');
            buscar();
        };

        // El chip abre el modal; si el click cae en la "x", limpia en su lugar (la "x"
        // vive dentro del boton, asi que un solo handler cubre ambos casos).
        trigger.addEventListener('click', (e) => {
            if (e.target.closest(`.${claseClear}`)) {
                e.stopPropagation();
                limpiar();
                return;
            }
            abrirSelectorEntidad(modal);
        });

        // La "x" es un span con role=button: Enter/Espacio tambien limpian.
        trigger.addEventListener('keydown', (e) => {
            if (e.target.closest(`.${claseClear}`) && (e.key === 'Enter' || e.key === ' ')) {
                e.preventDefault();
                e.stopPropagation();
                limpiar();
            }
        });

        // El modal avisa la eleccion; aplico el filtro con la entidad elegida.
        modal.addEventListener('selector-entidad:elegir', (e) => {
            setEstado(e.detail.id, e.detail.principal);
            buscar();
        });
    };

    configurarChipFiltro(clienteCont, modalCliente, {
        prefijo: 'deu-cliente',
        etiquetaVacia: 'Cliente',
        ariaLimpiar: 'Quitar filtro de cliente',
    });
    configurarChipFiltro(productoCont, modalProducto, {
        prefijo: 'deu-producto',
        etiquetaVacia: 'Producto',
        ariaLimpiar: 'Quitar filtro de producto',
    });

    // Chips de tipo (saldo/cobros/pagos): seleccion unica, siempre hay uno activo.
    // "Saldo" (data-tipo vacio) es el estado por defecto y el que se muestra al buscar
    // un cliente; las tarjetas muestran el neto a cobrar − a pagar. Clickear el que ya
    // esta activo no hace nada, igual que el segmentado de valuacion.
    chipsTipo.forEach((chip) => {
        chip.addEventListener('click', () => {
            if (chip.classList.contains('is-active')) return;
            chipsTipo.forEach((c) => c.classList.remove('is-active'));
            chip.classList.add('is-active');
            buscar();
        });
    });

    // Segmentado de valuacion: seleccion unica, siempre hay una activa. Clickear la
    // que ya esta activa no hace nada (a diferencia de los chips, no se puede apagar).
    optsValuacion.forEach((opt) => {
        opt.addEventListener('click', () => {
            if (opt.classList.contains('is-active')) return;
            optsValuacion.forEach((o) => {
                const activo = o === opt;
                o.classList.toggle('is-active', activo);
                o.setAttribute('aria-pressed', String(activo));
            });
            buscar();
        });
    });

    // ---------------------------------------------------------------------------
    // Filtro por fecha (componente compartido)
    // ---------------------------------------------------------------------------
    // filtro_fechas.js administra el popover y avisa con 'filtrofechas:cambio' al
    // aplicar o limpiar; aca lo traducimos a la busqueda AJAX. El estado (desde/
    // hasta) ya vive en los data-* de #filtro-fechas, que buscar() lee.
    document.addEventListener('filtrofechas:cambio', () => buscar());

    vincularPaginacion();
});
