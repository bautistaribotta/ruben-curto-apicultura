document.addEventListener('DOMContentLoaded', () => {
    // Selecciono los elementos del DOM que voy a usar para la búsqueda
    const inputBusqueda = document.getElementById('buscar-deudor');
    const contenedorTabla = document.getElementById('tabla-deudores-container');
    const pildoras = document.querySelectorAll('#chips-orden .prod-chip');
    const chipsTipo = document.querySelectorAll('#chips-tipo .prod-chip');

    // Devuelve el orden actualmente seleccionado por las píldoras
    const ordenActivo = () => {
        const activa = document.querySelector('#chips-orden .prod-chip.is-active');
        return activa ? activa.dataset.orden : 'monto';
    };

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
        } else {
            url = new URL(window.location.href);
            if (inputBusqueda) {
                url.searchParams.set('q', inputBusqueda.value);
            }
            url.searchParams.set('orden', ordenActivo());
            const tipo = tipoActivo();
            if (tipo) {
                url.searchParams.set('tipo', tipo);
            } else {
                url.searchParams.delete('tipo');
            }
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
            // Actualizo el contenedor con la nueva tabla
            contenedorTabla.innerHTML = html;
            
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

    // Agrego los event listeners iniciales
    if (inputBusqueda) {
        inputBusqueda.addEventListener('input', () => buscar());
    }

    // Píldoras de orden: marco la activa y vuelvo a buscar manteniendo el filtro
    pildoras.forEach((pildora) => {
        pildora.addEventListener('click', () => {
            if (pildora.classList.contains('is-active')) return;
            pildoras.forEach((p) => p.classList.remove('is-active'));
            pildora.classList.add('is-active');
            buscar();
        });
    });

    // Chips de tipo (cobros/pagos): seleccion unica o ninguna. Si clickeo el que
    // ya esta activo, lo apago y vuelvo a "todas"; si no, activo ese y apago el otro.
    chipsTipo.forEach((chip) => {
        chip.addEventListener('click', () => {
            const yaActivo = chip.classList.contains('is-active');
            chipsTipo.forEach((c) => c.classList.remove('is-active'));
            if (!yaActivo) {
                chip.classList.add('is-active');
            }
            buscar();
        });
    });

    vincularPaginacion();
});