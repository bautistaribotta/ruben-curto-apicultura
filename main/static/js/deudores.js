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

    // --- Filtro por fecha (chip + popover) ---
    // El contenedor guarda el estado APLICADO (desde/hasta en ISO) en sus data-*.
    // Es la fuente de verdad que lee buscar(); los inputs del popover son solo el
    // borrador hasta que el usuario toca "Aplicar".
    const fechas = document.getElementById('deu-fechas');
    const fechasTrigger = document.getElementById('deu-fechas-trigger');
    const fechasLabel = document.getElementById('deu-fechas-label');
    const fechasPop = document.getElementById('deu-fechas-pop');
    const segOpts = fechasPop ? fechasPop.querySelectorAll('.deu-seg__opt') : [];
    const inputDia = document.getElementById('deu-fechas-dia');
    const inputDesde = document.getElementById('deu-fechas-desde');
    const inputHasta = document.getElementById('deu-fechas-hasta');
    const btnAplicar = document.getElementById('deu-fechas-aplicar');
    const btnLimpiar = document.getElementById('deu-fechas-limpiar');

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
    // Filtro por fecha
    // ---------------------------------------------------------------------------
    if (fechas && fechasTrigger && fechasPop) {
        // Formatea una fecha ISO (yyyy-mm-dd) a dd/mm/yyyy o dd/mm (version corta).
        const fmt = (iso) => {
            const [y, m, d] = iso.split('-');
            return `${d}/${m}/${y}`;
        };
        const fmtCorto = (iso) => {
            const [, m, d] = iso.split('-');
            return `${d}/${m}`;
        };

        // Mismo criterio de etiqueta que el server (views.deudores): un solo dia,
        // rango cerrado, o rango abierto con un unico extremo.
        const armarLabel = (desde, hasta) => {
            if (desde && hasta && desde === hasta) return fmt(desde);
            if (desde && hasta) return `${fmtCorto(desde)} – ${fmt(hasta)}`;
            if (desde) return `Desde ${fmt(desde)}`;
            if (hasta) return `Hasta ${fmt(hasta)}`;
            return 'Fechas';
        };

        const modoActivo = () => {
            const opt = fechasPop.querySelector('.deu-seg__opt.is-active');
            return opt ? opt.dataset.modo : 'dia';
        };

        const setModo = (modo) => {
            segOpts.forEach((o) => o.classList.toggle('is-active', o.dataset.modo === modo));
            fechasPop.querySelectorAll('.deu-fechas__panel').forEach((p) => {
                p.hidden = p.dataset.panel !== modo;
            });
        };

        // Crea o quita la "x" para limpiar dentro del chip segun haya filtro activo.
        const actualizarClear = (activo) => {
            let clearEl = fechasTrigger.querySelector('.deu-fechas__clear');
            if (activo && !clearEl) {
                clearEl = document.createElement('span');
                clearEl.className = 'material-symbols-outlined deu-fechas__clear';
                clearEl.id = 'deu-fechas-clear';
                clearEl.setAttribute('role', 'button');
                clearEl.setAttribute('tabindex', '0');
                clearEl.setAttribute('aria-label', 'Quitar filtro de fechas');
                clearEl.textContent = 'close';
                fechasTrigger.appendChild(clearEl);
            } else if (!activo && clearEl) {
                clearEl.remove();
            }
        };

        // Vuelca el estado aplicado al chip (label, activo, boton de limpiar) y a los
        // data-* que lee buscar().
        const setEstado = (desde, hasta) => {
            fechas.dataset.desde = desde || '';
            fechas.dataset.hasta = hasta || '';
            const activo = Boolean(desde || hasta);
            fechasLabel.textContent = armarLabel(desde, hasta);
            fechasTrigger.classList.toggle('is-active', activo);
            actualizarClear(activo);
        };

        const abrirPop = () => {
            fechasPop.hidden = false;
            fechasTrigger.setAttribute('aria-expanded', 'true');
        };
        const cerrarPop = () => {
            fechasPop.hidden = true;
            fechasTrigger.setAttribute('aria-expanded', 'false');
        };
        const togglePop = () => (fechasPop.hidden ? abrirPop() : cerrarPop());

        const aplicar = () => {
            let desde = '';
            let hasta = '';
            if (modoActivo() === 'dia') {
                desde = inputDia.value;
                hasta = inputDia.value;
            } else {
                desde = inputDesde.value;
                hasta = inputHasta.value;
            }
            // Normalizo el rango invertido para que el label coincida con lo que
            // devuelve el server (que tambien lo normaliza).
            if (desde && hasta && desde > hasta) {
                [desde, hasta] = [hasta, desde];
            }
            setEstado(desde, hasta);
            cerrarPop();
            buscar();
        };

        const limpiar = () => {
            if (inputDia) inputDia.value = '';
            if (inputDesde) inputDesde.value = '';
            if (inputHasta) inputHasta.value = '';
            setEstado('', '');
            cerrarPop();
            buscar();
        };

        // Rehidrato el popover con el estado que vino del server: infiero el modo a
        // partir de si las dos fechas coinciden (un dia) o no (rango).
        const dIni = fechas.dataset.desde;
        const hIni = fechas.dataset.hasta;
        if (dIni && hIni && dIni === hIni) {
            setModo('dia');
            if (inputDia) inputDia.value = dIni;
        } else if (dIni || hIni) {
            setModo('rango');
            if (inputDesde) inputDesde.value = dIni;
            if (inputHasta) inputHasta.value = hIni;
        } else {
            setModo('dia');
        }

        // El chip abre/cierra el popover; si el click cae en la "x", limpia en su lugar
        // (la "x" vive dentro del boton, asi que un solo handler cubre ambos casos).
        fechasTrigger.addEventListener('click', (e) => {
            if (e.target.closest('.deu-fechas__clear')) {
                e.stopPropagation();
                limpiar();
                return;
            }
            togglePop();
        });

        segOpts.forEach((opt) => {
            opt.addEventListener('click', () => setModo(opt.dataset.modo));
        });

        if (btnAplicar) btnAplicar.addEventListener('click', aplicar);
        if (btnLimpiar) btnLimpiar.addEventListener('click', limpiar);

        // Enter dentro de cualquier input del popover aplica.
        fechasPop.querySelectorAll('.deu-campo__input').forEach((inp) => {
            inp.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    aplicar();
                }
            });
        });

        // Cierro al hacer click fuera del filtro o con Escape.
        document.addEventListener('click', (e) => {
            if (!fechasPop.hidden && !fechas.contains(e.target)) {
                cerrarPop();
            }
        });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && !fechasPop.hidden) {
                cerrarPop();
                fechasTrigger.focus();
            }
        });
    }

    vincularPaginacion();
});
