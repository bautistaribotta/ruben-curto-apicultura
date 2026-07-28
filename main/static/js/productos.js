/**
 * -----------------------------------------------------------------------------
 * 1. UTILIDADES GENERALES (BÚSQUEDA, FILTRADO Y PAGINACIÓN)
 * -----------------------------------------------------------------------------
 */

// Selecciono los elementos del DOM necesarios
const inputBusqueda = document.getElementById('buscar-producto');
const filtroCategoria = document.getElementById('filtro-categoria');
const contenedorTabla = document.getElementById('tabla-productos-container');

/**
 * Creo esta función para buscar productos y aplicar los filtros de categoría
 * usando AJAX. No recarga la página entera.
 * @param {string|null} urlString - URL opcional (ej: para paginación).
 */
const buscar = (urlString = null) => {
  if (!inputBusqueda || !filtroCategoria || !contenedorTabla) return;

  const q = inputBusqueda.value;
  const categoria = filtroCategoria.value;
  let url;
  
  if (urlString) {
    url = new URL(urlString, window.location.origin);
  } else {
    url = new URL(window.location.href);
    url.searchParams.set('q', q);
    url.searchParams.set('categoria', categoria);
    url.searchParams.delete('page');
  }

  fetch(url, {
    headers: {
      'X-Requested-With': 'XMLHttpRequest',
    },
  })
    .then((response) => response.text())
    .then((html) => {
      contenedorTabla.innerHTML = html;
      window.history.pushState({}, '', url);
      vincularPaginacion();
    })
    .catch((error) => console.error('Error en la búsqueda:', error));
};

/**
 * Creo esta función para que los enlaces de paginación funcionen por AJAX.
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

// Asigno los eventos iniciales a la busqueda y a las pildoras de categoria
if (inputBusqueda) inputBusqueda.addEventListener('input', () => buscar());

const chipsCategoria = document.getElementById('chips-categoria');
if (chipsCategoria) {
  chipsCategoria.addEventListener('click', (e) => {
    const chip = e.target.closest('.prod-chip');
    if (!chip) return;

    chipsCategoria.querySelectorAll('.prod-chip').forEach((c) => c.classList.remove('is-active'));
    chip.classList.add('is-active');

    if (filtroCategoria) filtroCategoria.value = chip.dataset.categoria;
    buscar();
  });
}

vincularPaginacion();

/**
 * -----------------------------------------------------------------------------
 * 2. CONTROLADORES DE PANELES (NUEVO/EDITAR)
 * -----------------------------------------------------------------------------
 */

/**
 * Creo esta función para limpiar el panel lateral y prepararlo para registrar
 * un nuevo producto desde cero.
 */
const prepararPanelNuevoProducto = () => {
  // Restauro los textos originales
  document.querySelector('#slide-over-panel h3').innerText = 'Nuevo Producto';
  document.querySelector('#slide-over-panel .texto-cabecera p').innerText = 'Complete los detalles para el inventario';
  document.querySelector('.boton-primario').innerText = 'Guardar Producto';
  document.querySelector('.icono-contenedor span').innerText = 'inventory_2';

  // Limpio el formulario y el ID oculto
  document.getElementById('form-producto').reset();
  document.getElementById('id_producto').value = '';
  // Stock solo se carga en el alta: muestro y habilito el campo
  document.getElementById('campo-stock-container').style.display = 'flex';
  document.getElementById('stock').disabled = false;

  if (typeof abrirSlideOver === 'function') abrirSlideOver();
};

  /**
  * Creo esta función para traer la información de un producto desde la API
  * y llenar los campos del panel lateral para editarlo.
  * @param {string|number} id - El ID del producto
  */
  const prepararPanelEditarProducto = (id) => {
  fetch(`/api/productos/${id}/`)
    .then((response) => response.json())
    .then((producto) => {
      // Actualizo textos e iconos para indicar "Edición"
      document.querySelector('#slide-over-panel h3').innerText = 'Editar Producto';
      document.querySelector('#slide-over-panel .texto-cabecera p').innerText = 'Modifique los datos del producto';
      document.querySelector('.boton-primario').innerText = 'Actualizar Producto';
      document.querySelector('.icono-contenedor span').innerText = 'edit_square';

      // Relleno el formulario con los datos reales
      document.getElementById('id_producto').value = producto.id;
      document.getElementById('nombre').value = producto.nombre;
      document.getElementById('categoria').value = producto.categoria;
      // La API devuelve el Decimal como "1500.00". El formulario trabaja con
      // precios enteros, asi que me quedo con la parte entera y la muestro
      // con separador de miles.
      ponerValorMiles(document.getElementById('precio'), producto.precio.split('.')[0]);

      // Oculto y deshabilito el stock: al editar no se modifica (se maneja en el
      // modal de agregar/quitar). Deshabilitado, ademas, no viaja en el submit.
      document.getElementById('campo-stock-container').style.display = 'none';
      document.getElementById('stock').disabled = true;

      if (typeof abrirSlideOver === 'function') abrirSlideOver();
    })
    .catch((error) => {
      console.error(error);
      if (typeof notificarErrorModal === 'function') {
        notificarErrorModal('Error al cargar los datos del producto');
      }
    });
};

/**
 * -----------------------------------------------------------------------------
 * 3. DELEGACIÓN DE EVENTOS (TABLA)
 * -----------------------------------------------------------------------------
 */

/**
 * Agrego un event listener general para escuchar los clicks de los botones
 * en cualquier parte de la tabla sin tener que asignar un evento por fila.
 */
document.addEventListener('click', (e) => {
  const botonEditar = e.target.closest('.boton-icono.editar');
  const botonEliminar = e.target.closest('.boton-icono.eliminar');
  const botonAgregarStock = e.target.closest('.boton-icono.agregar-stock');

  if (botonEditar) {
    const id = botonEditar.dataset.id;
    prepararPanelEditarProducto(id);
  }

  if (botonEliminar) {
    const id = botonEliminar.dataset.id;
    const nombre = botonEliminar.dataset.nombre;

    // Configuro el panel modal de eliminación
    document.getElementById('id_eliminar').value = id;
    document.getElementById('texto-confirmacion-eliminar').innerHTML = `¿Confirma que quiere eliminar el producto <b>${nombre}</b>?`;

    if (typeof abrirPanelEliminar === 'function') abrirPanelEliminar();
  }

  if (botonAgregarStock) {
    const id = botonAgregarStock.dataset.id;
    const nombre = botonAgregarStock.dataset.nombre;
    const stock = botonAgregarStock.dataset.stock;
    
    // Configuro el modal de stock
    document.getElementById('id_producto_stock').value = id;
    document.getElementById('nombre-producto-stock').innerText = nombre;
    document.getElementById('cantidad-stock-actual').innerText = stock;
    
    // Resetear al estado "Añadir" (Segmented Control)
    const radioAñadir = document.getElementById('accion-añadir');
    if (radioAñadir) {
      radioAñadir.checked = true;
    }
    
    document.getElementById('cantidad-modificar').value = 1;
    
    const modalStock = document.getElementById('contenedor-modal-stock');
    if (modalStock) {
      modalStock.classList.add('abierto');
    }
  }
});

// Validación para campo de stock (avisa sobre puntos y comas)
const inputStock = document.getElementById('stock');
const errorStock = document.getElementById('error-stock');

if (inputStock && errorStock) {
  inputStock.addEventListener('input', (e) => {
    // Verificamos si hay error por decimales
    if (inputStock.validity.stepMismatch || inputStock.validity.badInput || inputStock.value.includes('.') || inputStock.value.includes(',')) {
      errorStock.style.display = 'block';
    } else {
      errorStock.style.display = 'none';
    }
  });

  inputStock.addEventListener('keydown', (e) => {
    if (e.key === '.' || e.key === ',') {
      errorStock.style.display = 'block';
    }
  });
}

// Autocapitalizar la primera letra al escribir en el nombre del producto
const inputNombreProducto = document.getElementById('nombre');
if (inputNombreProducto) {
  inputNombreProducto.addEventListener('input', (e) => {
    let valor = e.target.value;
    if (valor.length > 0) {
      e.target.value = valor.charAt(0).toUpperCase() + valor.slice(1);
    }
  });
}

// Lógica del modal de stock
const cerrarModalStock = () => {
  const modalStock = document.getElementById('contenedor-modal-stock');
  if (modalStock) {
    modalStock.classList.remove('abierto');
  }
};

window.cerrarModalStock = cerrarModalStock;

// Validación del formulario de stock antes de enviar
const formStock = document.getElementById('formulario-stock');
if (formStock) {
  formStock.addEventListener('submit', (e) => {
    const radioQuitar = document.getElementById('accion-quitar');
    const inputCantidad = document.getElementById('cantidad-modificar');
    const spanStockActual = document.getElementById('cantidad-stock-actual');
    
    if (radioQuitar && radioQuitar.checked) {
      const cantidad = parseInt(inputCantidad.value, 10) || 0;
      const stockActual = parseInt(spanStockActual.innerText, 10) || 0;
      
      if (cantidad > stockActual) {
        e.preventDefault(); // Detener el envío del formulario
        if (typeof crearToast === 'function') {
          crearToast('No se puede quitar más stock del existente.', 'error');
        } else {
          alert('No se puede quitar más stock del existente.');
        }
      }
    }
  });
}

// Hago accesibles las funciones que el HTML llama mediante "onclick"
window.prepararPanelNuevoProducto = prepararPanelNuevoProducto;