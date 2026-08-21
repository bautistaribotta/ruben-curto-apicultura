document.addEventListener('DOMContentLoaded', () => {
    const cuerpoCarrito = document.getElementById('cuerpo-carrito');
    const elementoTotal = document.getElementById('total-destacado');
    const inputBusqueda = document.querySelector('.input-busqueda');
    const contenedorTabla = document.getElementById('contenedor-tabla-compras');
    const carritoVacio = document.getElementById('carrito-vacio');
    const contadorCarrito = document.getElementById('contador-carrito');
    const botonVaciar = document.getElementById('boton-vaciar-carrito');

    // Formateador en formato argentino (separador de miles con punto)
    const formatoMoneda = new Intl.NumberFormat('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

    // Los atributos data-* llegan con coma decimal por la localizacion de Django
    function normalizarDecimal(valor) {
        return parseFloat(String(valor).replace(',', '.')) || 0;
    }

    // Clave en sessionStorage para persistir el carrito de compra
    const STORAGE_KEY = 'carrito_compra';

    // Modo edición: el template inyecta los datos de la compra a editar
    const scriptEdicion = document.getElementById('datos-edicion');
    const edicion = scriptEdicion ? JSON.parse(scriptEdicion.textContent) : null;

    // Precarga el carrito con los ítems de la compra que se está editando
    function cargarEdicion() {
        edicion.items.forEach(item => {
            if (item.tipo === 'granel') {
                crearFilaGranel(item.id, item.nombre, item.precio, item.cantidad);
                return;
            }
            crearFilaCarrito(item.id, item.nombre, item.cantidad, item.precio, item.bloqueado);
        });
        actualizarTotal();
        actualizarVistaResumen();
    }

    // =============================================
    //  PERSISTENCIA DEL CARRITO (sessionStorage)
    // =============================================

    function guardarCarrito() {
        const filas = cuerpoCarrito.querySelectorAll('.cart-item');
        const items = [];
        filas.forEach(fila => {
            if (fila.dataset.tipo === 'granel') {
                items.push({
                    tipo: 'granel',
                    id: fila.dataset.granelId,
                    nombre: fila.querySelector('.cart-item__name').textContent,
                    kilos: fila.querySelector('.input-kilos').value,
                    precio: fila.querySelector('.input-precio-item').value
                });
                return;
            }
            items.push({
                id: fila.dataset.id,
                nombre: fila.querySelector('.cart-item__name').textContent,
                cantidad: parseInt(fila.querySelector('.input-cantidad').value),
                precio: fila.querySelector('.input-precio-item').value,
                bloqueado: fila.dataset.bloqueado === '1'
            });
        });
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify(items));
    }

    function restaurarCarrito() {
        const navegacion = performance.getEntriesByType('navigation')[0];
        const esRecarga = navegacion && navegacion.type === 'reload';

        if (!esRecarga) {
            sessionStorage.removeItem(STORAGE_KEY);
            return;
        }

        const datos = sessionStorage.getItem(STORAGE_KEY);
        if (!datos) return;

        const items = JSON.parse(datos);
        items.forEach(item => {
            if (item.tipo === 'granel') {
                crearFilaGranel(item.id, item.nombre, item.precio, item.kilos);
                return;
            }
            crearFilaCarrito(item.id, item.nombre, item.cantidad, item.precio, item.bloqueado);
        });
        actualizarTotal();
        actualizarVistaResumen();
    }

    function limpiarCarritoStorage() {
        sessionStorage.removeItem(STORAGE_KEY);
    }

    // =============================================
    //  ESTADO DEL RESUMEN (vacío / contador)
    // =============================================

    function actualizarVistaResumen() {
        const cantidadItems = cuerpoCarrito.querySelectorAll('.cart-item').length;
        const hayItems = cantidadItems > 0;

        carritoVacio.classList.toggle('oculto', hayItems);
        cuerpoCarrito.classList.toggle('oculto', !hayItems);
        botonVaciar.classList.toggle('oculto', !hayItems);
        contadorCarrito.classList.toggle('oculto', !hayItems);
        contadorCarrito.textContent = cantidadItems;
    }

    // =============================================
    //  LÓGICA DEL CARRITO
    // =============================================

    function vincularBotonesAgregar() {
        const botones = contenedorTabla.querySelectorAll('.boton-agregar-producto');
        botones.forEach(boton => {
            boton.addEventListener('click', function () {
                agregarAlCarrito(this.dataset.id, this.dataset.nombre);
            });
        });
    }

    function agregarAlCarrito(id, nombre) {
        const filaExistente = cuerpoCarrito.querySelector(`.cart-item[data-id="${id}"]`);

        if (filaExistente) {
            const inputCantidad = filaExistente.querySelector('.input-cantidad');
            inputCantidad.value = parseInt(inputCantidad.value) + 1;
            actualizarSubtotalFila(filaExistente);
        } else {
            crearFilaCarrito(id, nombre, 1, '');
        }

        actualizarTotal();
        guardarCarrito();
    }

    function crearFilaCarrito(id, nombre, cantidad, precio, bloqueado = false) {
        const fila = document.createElement('div');
        fila.className = 'cart-item';
        fila.dataset.id = id;
        // Producto dado de baja: la línea viaja igual pero queda congelada
        // (sin cambiar cantidad ni precio, sin poder quitarla del carrito)
        if (bloqueado) fila.dataset.bloqueado = '1';

        fila.innerHTML = `
            <div class="cart-item__top">
                <div>
                    <div class="cart-item__name" title="${nombre}">${nombre}</div>
                    ${bloqueado ? '<span class="cart-item__badge-baja"><span class="material-symbols-outlined">lock</span>Producto dado de baja</span>' : ''}
                </div>
                <button type="button" class="cart-item__rm" title="Quitar">
                    <span class="material-symbols-outlined">close</span>
                </button>
            </div>
            <div class="cart-item__ctrl">
                <div class="cart-stepper">
                    <button type="button" data-step="menos" title="Restar"><span class="material-symbols-outlined">remove</span></button>
                    <input type="number" class="input-cantidad" value="${cantidad}" min="1">
                    <button type="button" data-step="mas" title="Sumar"><span class="material-symbols-outlined">add</span></button>
                </div>
                <div class="cart-priceedit">
                    <span class="cart-priceedit__cur">$</span>
                    <input type="number" class="input-precio-item" placeholder="0.00" min="0" step="0.01" value="${precio}">
                </div>
            </div>
            <div class="cart-item__sub2">
                <span class="cart-item__sublabel">Subtotal</span>
                <span class="cart-item__subval">$ 0.00</span>
            </div>
        `;

        const inputCantidad = fila.querySelector('.input-cantidad');
        const botonMenos = fila.querySelector('[data-step="menos"]');
        const botonMas = fila.querySelector('[data-step="mas"]');
        const inputPrecio = fila.querySelector('.input-precio-item');

        if (bloqueado) {
            fila.classList.add('cart-item--bloqueado');
            inputCantidad.disabled = true;
            inputPrecio.disabled = true;
            botonMenos.disabled = true;
            botonMas.disabled = true;
            const botonQuitar = fila.querySelector('.cart-item__rm');
            botonQuitar.disabled = true;
            botonQuitar.title = 'Producto dado de baja: no se puede quitar';

            cuerpoCarrito.appendChild(fila);
            actualizarSubtotalFila(fila);
            actualizarVistaResumen();
            return;
        }

        // Escritura libre: no forzamos el valor; la validación se hace al confirmar
        function alCambiar() {
            actualizarSubtotalFila(fila);
            actualizarTotal();
            guardarCarrito();
        }

        // Quita el producto del carrito y limpia el resaltado
        function quitar() {
            fila.remove();
            actualizarTotal();
            actualizarVistaResumen();
            guardarCarrito();
            const btnTabla = contenedorTabla.querySelector(`.boton-agregar-producto[data-id="${id}"]`);
            if (btnTabla) btnTabla.classList.remove('is-incart');
        }

        inputCantidad.addEventListener('input', alCambiar);
        inputPrecio.addEventListener('input', alCambiar);

        botonMenos.addEventListener('click', function () {
            const actual = parseInt(inputCantidad.value);
            if (isNaN(actual) || actual <= 1) {
                // Con 1 unidad, reducir saca el producto del carrito
                quitar();
            } else {
                inputCantidad.value = actual - 1;
                alCambiar();
            }
        });

        botonMas.addEventListener('click', function () {
            inputCantidad.value = (parseInt(inputCantidad.value) || 0) + 1;
            alCambiar();
        });

        const botonEliminar = fila.querySelector('.cart-item__rm');
        botonEliminar.addEventListener('click', quitar);

        cuerpoCarrito.appendChild(fila);
        alCambiar();
        actualizarVistaResumen();
        
        const btnTabla = contenedorTabla.querySelector(`.boton-agregar-producto[data-id="${id}"]`);
        if(btnTabla) btnTabla.classList.add('is-incart');
    }

    function actualizarSubtotalFila(fila) {
        const cantidad = parseInt(fila.querySelector('.input-cantidad').value) || 0;
        const precio = parseFloat(fila.querySelector('.input-precio-item').value) || 0;
        const subtotal = cantidad * precio;
        fila.querySelector('.cart-item__subval').textContent = `$ ${formatoMoneda.format(subtotal)}`;
    }

    // =============================================
    //  ARTICULOS A GRANEL (kilos desde cotizaciones)
    // =============================================

    function vincularBotonesGranel() {
        contenedorTabla.querySelectorAll('.boton-agregar-granel').forEach(boton => {
            boton.addEventListener('click', function () {
                const id = this.dataset.id;
                const filaExistente = cuerpoCarrito.querySelector(`.cart-item[data-granel-id="${id}"]`);

                if (filaExistente) {
                    // Ya esta en el carrito: llevo el foco al input de kilos
                    filaExistente.querySelector('.input-kilos').focus();
                    return;
                }

                // El precio arranca precargado con la cotizacion del dia, pero es editable.
                // Los kilos arrancan vacios: se cargan segun la pesada real.
                crearFilaGranel(id, this.dataset.nombre, normalizarDecimal(this.dataset.precio), '');
                actualizarTotal();
                guardarCarrito();
            });
        });
    }

    function crearFilaGranel(idCotizacion, nombre, precio, kilos) {
        const fila = document.createElement('div');
        fila.className = 'cart-item cart-item--granel';
        // Prefijo "granel-" en data-id para que nunca colisione con un id de producto
        fila.dataset.id = `granel-${idCotizacion}`;
        fila.dataset.granelId = idCotizacion;
        fila.dataset.tipo = 'granel';

        fila.innerHTML = `
            <div class="cart-item__top">
                <div>
                    <div class="cart-item__name" title="${nombre}">${nombre}</div>
                    <span class="granel-tag"><span class="material-symbols-outlined">scale</span>Por kg</span>
                </div>
                <button type="button" class="cart-item__rm" title="Quitar">
                    <span class="material-symbols-outlined">close</span>
                </button>
            </div>
            <div class="cart-item__ctrl">
                <div class="cart-kg">
                    <input type="number" class="input-kilos" placeholder="0" min="0.01" step="0.01" value="${kilos}">
                    <span class="cart-kg__u">kg</span>
                </div>
                <div class="cart-priceedit">
                    <span class="cart-priceedit__cur">$</span>
                    <input type="number" class="input-precio-item" placeholder="0.00" min="0" step="0.01" value="${precio}">
                    <span class="cart-priceedit__u">/kg</span>
                </div>
            </div>
            <div class="cart-item__sub2">
                <span class="cart-item__sublabel">Subtotal</span>
                <span class="cart-item__subval">$ 0,00</span>
            </div>
        `;

        const inputKilos = fila.querySelector('.input-kilos');
        const inputPrecio = fila.querySelector('.input-precio-item');

        function alCambiar() {
            actualizarSubtotalGranel(fila);
            actualizarTotal();
            guardarCarrito();
        }

        function quitar() {
            fila.remove();
            actualizarTotal();
            actualizarVistaResumen();
            guardarCarrito();
            const btnTabla = contenedorTabla.querySelector(`.boton-agregar-granel[data-id="${idCotizacion}"]`);
            if (btnTabla) btnTabla.classList.remove('is-incart');
        }

        inputKilos.addEventListener('input', alCambiar);
        inputPrecio.addEventListener('input', alCambiar);
        fila.querySelector('.cart-item__rm').addEventListener('click', quitar);

        cuerpoCarrito.appendChild(fila);
        actualizarSubtotalGranel(fila);
        actualizarVistaResumen();

        const btnTabla = contenedorTabla.querySelector(`.boton-agregar-granel[data-id="${idCotizacion}"]`);
        if (btnTabla) btnTabla.classList.add('is-incart');

        // Foco directo al input de kilos para cargar la pesada sin clicks extra
        inputKilos.focus();
    }

    function actualizarSubtotalGranel(fila) {
        const kilos = parseFloat(fila.querySelector('.input-kilos').value) || 0;
        const precio = parseFloat(fila.querySelector('.input-precio-item').value) || 0;
        fila.querySelector('.cart-item__subval').textContent = `$ ${formatoMoneda.format(kilos * precio)}`;
    }

    function actualizarTotal() {
        let total = 0;
        const filasCarrito = cuerpoCarrito.querySelectorAll('.cart-item');

        filasCarrito.forEach(fila => {
            const precio = parseFloat(fila.querySelector('.input-precio-item').value) || 0;
            if (fila.dataset.tipo === 'granel') {
                const kilos = parseFloat(fila.querySelector('.input-kilos').value) || 0;
                total += kilos * precio;
                return;
            }
            const cantidad = parseInt(fila.querySelector('.input-cantidad').value) || 0;
            total += cantidad * precio;
        });

        elementoTotal.textContent = `$ ${formatoMoneda.format(total)}`;
    }

    botonVaciar.addEventListener('click', function () {
        // Las filas bloqueadas (productos dados de baja) no se pueden quitar
        cuerpoCarrito.querySelectorAll('.cart-item').forEach(fila => {
            if (fila.dataset.bloqueado !== '1') fila.remove();
        });
        actualizarTotal();
        actualizarVistaResumen();
        guardarCarrito();
        contenedorTabla.querySelectorAll('.boton-agregar-producto').forEach(btn => btn.classList.remove('is-incart'));
        contenedorTabla.querySelectorAll('.boton-agregar-granel').forEach(btn => btn.classList.remove('is-incart'));
    });

    // =============================================
    //  BUSCADOR DE PRODUCTOS (AJAX)
    // =============================================

    let timeoutBusqueda = null;
    const chips = document.querySelectorAll('.cart-chip');
    const chipActivo = document.querySelector('.cart-chip.is-active');
    let categoriaActual = chipActivo ? (chipActivo.dataset.categoria || '') : '';

    function buscarProductos(urlString = null) {
        let url;

        if (urlString) {
            url = new URL(urlString, window.location.origin);
        } else {
            url = new URL(window.location.href);
            url.searchParams.set('q', inputBusqueda.value.trim());
            url.searchParams.delete('page');
            if (categoriaActual) {
                url.searchParams.set('categoria', categoriaActual);
            } else {
                url.searchParams.delete('categoria');
            }
        }

        fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(response => response.text())
            .then(html => {
                contenedorTabla.innerHTML = html;
                vincularBotonesAgregar();
                vincularBotonesGranel();
                vincularPaginacion();

                // Vuelvo a resaltar los botones de lo que ya esta en el carrito,
                // tanto productos envasados como articulos a granel
                cuerpoCarrito.querySelectorAll('.cart-item').forEach(fila => {
                    const selector = fila.dataset.tipo === 'granel'
                        ? `.boton-agregar-granel[data-id="${fila.dataset.granelId}"]`
                        : `.boton-agregar-producto[data-id="${fila.dataset.id}"]`;
                    const btn = contenedorTabla.querySelector(selector);
                    if (btn) btn.classList.add('is-incart');
                });
            })
            .catch(error => console.error('Error en la búsqueda:', error));
    }

    function vincularPaginacion() {
        const linksPaginacion = contenedorTabla.querySelectorAll('.paginacion-botones a');

        linksPaginacion.forEach(link => {
            link.addEventListener('click', function (e) {
                e.preventDefault();
                buscarProductos(this.href);
            });
        });
    }

    inputBusqueda.addEventListener('input', function () {
        clearTimeout(timeoutBusqueda);
        timeoutBusqueda = setTimeout(() => {
            buscarProductos();
        }, 300);
    });

    // Filtro por categoría (chips)
    chips.forEach(chip => {
        chip.addEventListener('click', function () {
            chips.forEach(c => c.classList.remove('is-active'));
            this.classList.add('is-active');
            categoriaActual = this.dataset.categoria || '';
            buscarProductos();
        });
    });

    // =============================================
    //  CONFIRMAR COMPRA (enviar al servidor)
    // =============================================

    const botonConfirmar = document.querySelector('.boton-confirmar-operacion');

    function obtenerCSRFToken() {
        const cookie = document.cookie.split('; ').find(c => c.startsWith('csrftoken='));
        return cookie ? cookie.split('=')[1] : '';
    }

    function avisar(mensaje) {
        if (typeof notificarError === 'function') {
            notificarError(mensaje);
        } else {
            alert(mensaje);
        }
    }

    botonConfirmar.addEventListener('click', function () {
        const filas = cuerpoCarrito.querySelectorAll('.cart-item');

        if (filas.length === 0) {
            avisar('Agregá al menos un producto antes de confirmar.');
            return;
        }

        // Recopilar los items del carrito validando cantidad y precio
        const items = [];
        let precioInvalido = false;
        let cantidadInvalida = false;

        filas.forEach(fila => {
            const precioStr = fila.querySelector('.input-precio-item').value.trim();
            const precio = parseFloat(precioStr);

            if (isNaN(precio) || precio <= 0) {
                precioInvalido = true;
            }

            if (fila.dataset.tipo === 'granel') {
                const kilos = parseFloat(fila.querySelector('.input-kilos').value);

                if (isNaN(kilos) || kilos <= 0) {
                    cantidadInvalida = true;
                }

                items.push({
                    id_cotizacion: fila.dataset.granelId,
                    cantidad: kilos,
                    precio_unitario: precioStr
                });
                return;
            }

            const cantidad = parseInt(fila.querySelector('.input-cantidad').value);

            if (isNaN(cantidad) || cantidad < 1) {
                cantidadInvalida = true;
            }

            items.push({
                id_producto: fila.dataset.id,
                cantidad: cantidad,
                precio_unitario: precioStr
            });
        });

        if (cantidadInvalida) {
            avisar('Revisá las cantidades: cada línea necesita un número válido mayor a 0.');
            return;
        }

        if (precioInvalido) {
            avisar('Cargá un precio mayor a 0 en todos los productos.');
            return;
        }

        const metodoPagoSeleccionado = document.querySelector('input[name="metodo_pago"]:checked');

        if (!metodoPagoSeleccionado) {
            avisar('Elegí un método de pago (cuenta corriente o contado) para registrar la compra.');
            return;
        }

        const metodoPago = metodoPagoSeleccionado.value;

        // Fecha anterior a hoy sin cotizaciones de origen confirmadas: se
        // reabre el modal en vez de mandar la compra incompleta
        if (typeof faltanCotizacionesHistoricas === 'function' && faltanCotizacionesHistoricas()) {
            abrirModalCotizacionesHistoricas();
            return;
        }

        // Guardo el contenido original del boton ("Confirmar compra" o "Guardar cambios")
        const textoBotonOriginal = botonConfirmar.innerHTML;
        botonConfirmar.disabled = true;
        botonConfirmar.innerHTML = 'Procesando...';

        fetch(window.location.href, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': obtenerCSRFToken(),
            },
            body: JSON.stringify({
                items: items,
                metodo_pago: metodoPago,
                tipo_operacion: 'compra',
                // null si la compra es de hoy; "YYYY-MM-DD" si se cargo una fecha distinta
                fecha: typeof obtenerFechaOperacion === 'function' ? obtenerFechaOperacion() : null,
                // valores de miel menor a 50 mm, dolar oficial y cera operculo de aquel
                // dia; null salvo que la fecha sea anterior a hoy
                cotizaciones_historicas: typeof obtenerCotizacionesHistoricas === 'function' ? obtenerCotizacionesHistoricas() : null,
                // nota opcional que se imprime en el remito
                observaciones: typeof obtenerObservacion === 'function' ? obtenerObservacion() : '',
                // id de la compra a editar; null cuando se crea una nueva
                editar: edicion ? edicion.id : null,
            }),
        })
            .then(response => response.json().then(data => ({ ok: response.ok, data })))
            .then(({ ok, data }) => {
                if (ok && data.ok) {
                    limpiarCarritoStorage();
                    if (data.editada) {
                        window.location.href = `/informacion_operacion/${data.id_operacion}/`;
                    } else if (data.id_viaje) {
                        window.location.href = `/informacion_viaje/${data.id_viaje}/`;
                    } else {
                        window.location.href = `/informacion_clientes/${data.id_cliente}/`;
                    }
                } else {
                    notificarErrorModal(data.error || 'Algo salió mal. Por favor, volvé a intentarlo.');
                    botonConfirmar.disabled = false;
                    botonConfirmar.innerHTML = textoBotonOriginal;
                }
            })
            .catch(error => {
                console.error('Error en la petición:', error);
                notificarErrorModal('Algo salió mal. Por favor, volvé a intentarlo.');
                botonConfirmar.disabled = false;
                botonConfirmar.innerHTML = textoBotonOriginal;
            });
    });

    window.addEventListener('beforeunload', function () {
        if (cuerpoCarrito.querySelectorAll('.cart-item').length > 0) guardarCarrito();
    });

    // En modo edición el carrito se precarga con la compra; si no, se
    // restaura el que quedó en sessionStorage tras una recarga
    if (edicion) {
        cargarEdicion();
    } else {
        restaurarCarrito();
    }
    actualizarVistaResumen();
    vincularBotonesAgregar();
    vincularBotonesGranel();
    vincularPaginacion();
});
