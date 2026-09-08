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
 * Unidad de venta: el producto se cuenta por unidad (tabla de productos) o se
 * pesa por kilo (tabla de productos por kg). La eleccion cambia el precio que
 * se pide, el paso del stock y el endpoint contra el que trabaja el panel.
 */
const inputUnidadVenta = document.getElementById('unidad_venta');
const radioPorUnidad = document.getElementById('venta-por-unidad');
const radioPorKilo = document.getElementById('venta-por-kilo');
const notaUnidadVenta = document.getElementById('nota-venta');

const esPorKilo = () => inputUnidadVenta && inputUnidadVenta.value === 'kg';

/**
 * Deja el formulario hablando en la unidad elegida: marca la tarjeta, guarda el
 * valor que viaja en el POST y ajusta las etiquetas de precio y stock. Sin
 * unidad ('' al abrir el alta) las dos tarjetas quedan sin marcar y las
 * etiquetas se muestran neutras hasta que el usuario elija.
 * @param {string} unidad - 'kg', 'unidad' o '' para el estado sin elegir
 */
const aplicarUnidadVenta = (unidad) => {
  if (!inputUnidadVenta) return;

  const elegida = unidad === 'kg' || unidad === 'unidad';
  const porKilo = unidad === 'kg';
  inputUnidadVenta.value = elegida ? unidad : '';

  if (radioPorUnidad) radioPorUnidad.checked = elegida && !porKilo;
  if (radioPorKilo) radioPorKilo.checked = porKilo;

  const etiquetaPrecio = document.getElementById('etiqueta-precio');
  if (etiquetaPrecio) {
    if (!elegida) etiquetaPrecio.innerText = 'Precio';
    else etiquetaPrecio.innerText = porKilo ? 'Precio por kilo' : 'Precio Unitario';
  }

  const etiquetaStock = document.getElementById('etiqueta-stock');
  if (etiquetaStock) {
    etiquetaStock.innerText = porKilo ? 'Stock inicial en kilos (opcional)' : 'Stock Inicial (Opcional)';
  }

  const campoStock = document.getElementById('stock');
  if (campoStock) {
    campoStock.step = porKilo ? '0.01' : '1';
    campoStock.placeholder = porKilo ? '0.00' : '0';
  }

  const mensajeStock = document.getElementById('error-stock');
  if (mensajeStock) {
    mensajeStock.innerText = porKilo
      ? 'Los kilos se escriben con punto decimal (ej: 12.5).'
      : 'El stock debe ser un número entero (sin puntos ni comas).';
    mensajeStock.style.display = 'none';
  }
};

// Al editar, la unidad de venta queda fija: el producto ya vive en una tabla
const bloquearUnidadVenta = (bloqueada) => {
  if (radioPorUnidad) radioPorUnidad.disabled = bloqueada;
  if (radioPorKilo) radioPorKilo.disabled = bloqueada;
  if (notaUnidadVenta) notaUnidadVenta.hidden = !bloqueada;
};

[radioPorUnidad, radioPorKilo].forEach((radio) => {
  if (radio) radio.addEventListener('change', () => aplicarUnidadVenta(radio.value));
});

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
  // Si venia de editar un precio a granel, restauro el modo producto normal
  salirModoGranel();
  // La unidad de venta arranca sin elegir: es una decision del usuario
  aplicarUnidadVenta('');
  bloquearUnidadVenta(false);
  // Stock solo se carga en el alta: muestro y habilito el campo
  document.getElementById('campo-stock-container').style.display = 'flex';
  document.getElementById('stock').disabled = false;

  if (typeof abrirSlideOver === 'function') abrirSlideOver();
};

  /**
  * Creo esta función para traer la información de un producto desde la API
  * y llenar los campos del panel lateral para editarlo.
  * @param {string|number} id - El ID del producto
  * @param {string} unidad - 'kg' si el producto se pesa, 'unidad' si se cuenta
  */
  const prepararPanelEditarProducto = (id, unidad = 'unidad') => {
  const porKilo = unidad === 'kg';

  fetch(porKilo ? `/api/productos_por_kg/${id}/` : `/api/productos/${id}/`)
    .then((response) => response.json())
    .then((producto) => {
      // Actualizo textos e iconos para indicar "Edición"
      document.querySelector('#slide-over-panel h3').innerText = 'Editar Producto';
      document.querySelector('#slide-over-panel .texto-cabecera p').innerText = 'Modifique los datos del producto';
      document.querySelector('.boton-primario').innerText = 'Actualizar Producto';
      document.querySelector('.icono-contenedor span').innerText = 'edit_square';

      // Si venia de editar un precio a granel, restauro el modo producto normal
      salirModoGranel();

      // La unidad de venta se muestra, bloqueada: no se cambia despues del alta
      aplicarUnidadVenta(unidad);
      bloquearUnidadVenta(true);

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
  const botonEditarGranel = e.target.closest('.editar-precio-granel');

  if (botonEditar) {
    const id = botonEditar.dataset.id;
    prepararPanelEditarProducto(id, botonEditar.dataset.unidad);
  }

  if (botonEditarGranel) {
    prepararPanelEditarPrecioGranel(botonEditarGranel.dataset);
  }

  if (botonEliminar) {
    const id = botonEliminar.dataset.id;
    const nombre = botonEliminar.dataset.nombre;

    // Configuro el panel modal de eliminación
    document.getElementById('id_eliminar').value = id;
    document.getElementById('unidad_venta_eliminar').value = botonEliminar.dataset.unidad || 'unidad';
    document.getElementById('texto-confirmacion-eliminar').innerHTML = `¿Confirma que quiere eliminar el producto <b>${nombre}</b>?`;

    if (typeof abrirPanelEliminar === 'function') abrirPanelEliminar();
  }

  if (botonAgregarStock) {
    const id = botonAgregarStock.dataset.id;
    const nombre = botonAgregarStock.dataset.nombre;
    const stock = botonAgregarStock.dataset.stock;
    const unidad = botonAgregarStock.dataset.unidad || 'unidad';
    const porKilo = unidad === 'kg';
    const abreviatura = porKilo ? 'kg' : 'uds';

    // Configuro el modal de stock
    document.getElementById('id_producto_stock').value = id;
    document.getElementById('unidad_venta_stock').value = unidad;
    document.getElementById('nombre-producto-stock').innerText = nombre;
    document.getElementById('unidad-medida-stock').innerText = abreviatura;

    // Muestro el stock con el formato de la tabla y guardo el valor crudo en el
    // dataset, que es el que compara la validacion antes de quitar
    const spanStock = document.getElementById('cantidad-stock-actual');
    const formateador = new Intl.NumberFormat('es-AR', { maximumFractionDigits: 2 });
    spanStock.dataset.stock = stock;
    spanStock.innerText = `${formateador.format(Number(stock))} ${abreviatura}`;

    // Resetear al estado "Añadir" (Segmented Control)
    const radioAñadir = document.getElementById('accion-añadir');
    if (radioAñadir) {
      radioAñadir.checked = true;
    }

    // El producto que se pesa admite fracciones de kilo; el que se cuenta, no
    const inputCantidad = document.getElementById('cantidad-modificar');
    inputCantidad.step = porKilo ? '0.01' : '1';
    inputCantidad.min = porKilo ? '0.01' : '1';
    inputCantidad.value = 1;

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
    // Verificamos si hay error por decimales (los kilos si los admiten)
    if (esPorKilo()) {
      errorStock.style.display = inputStock.validity.badInput ? 'block' : 'none';
      return;
    }

    if (inputStock.validity.stepMismatch || inputStock.validity.badInput || inputStock.value.includes('.') || inputStock.value.includes(',')) {
      errorStock.style.display = 'block';
    } else {
      errorStock.style.display = 'none';
    }
  });

  inputStock.addEventListener('keydown', (e) => {
    if (!esPorKilo() && (e.key === '.' || e.key === ',')) {
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
      // El texto viene formateado en es-AR: comparo contra el valor crudo
      const cantidad = parseFloat(inputCantidad.value) || 0;
      const stockActual = parseFloat(spanStockActual.dataset.stock) || 0;
      
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

/**
 * -----------------------------------------------------------------------------
 * 4. EDICION DE PRECIO A GRANEL (MIEL Y CERA POR KILO, SOLO STAFF)
 * -----------------------------------------------------------------------------
 * Reutiliza el mismo slide-over que la edicion de productos. El stock de estos
 * articulos se maneja en cotizaciones, asi que el nombre y la categoria se
 * muestran bloqueados y solo el precio queda editable. El guardado no usa el
 * submit normal del producto: va contra el endpoint de cotizaciones.
 */
const formProducto = document.getElementById('form-producto');

// Devuelve el slide-over al modo producto normal (nombre y categoria editables).
// Se llama al abrir el panel para alta o edicion de un producto envasado.
const salirModoGranel = () => {
  if (!formProducto) return;
  delete formProducto.dataset.modo;
  delete formProducto.dataset.articulo;
  document.getElementById('nombre').disabled = false;
  document.getElementById('categoria').disabled = false;
};

// Configura el slide-over para editar solo el precio de un articulo a granel.
const prepararPanelEditarPrecioGranel = (datos) => {
  if (!formProducto) return;

  document.querySelector('#slide-over-panel h3').innerText = 'Editar precio';
  document.querySelector('#slide-over-panel .texto-cabecera p').innerText = 'Solo se puede modificar el precio por kilo';
  document.querySelector('.boton-primario').innerText = 'Actualizar precio';
  document.querySelector('.icono-contenedor span').innerText = 'edit_square';

  formProducto.reset();
  aplicarUnidadVenta('kg');
  bloquearUnidadVenta(true);
  formProducto.dataset.modo = 'granel';
  formProducto.dataset.articulo = datos.articulo;
  document.getElementById('id_producto').value = '';

  // Nombre y categoria visibles pero bloqueados: solo el precio se edita
  const nombre = document.getElementById('nombre');
  nombre.value = datos.articulo;
  nombre.disabled = true;

  const categoria = document.getElementById('categoria');
  categoria.value = datos.categoria; // "Miel" o "Cera"
  categoria.disabled = true;

  ponerValorMiles(document.getElementById('precio'), datos.precio);

  // El stock no aplica: se gestiona desde cotizaciones
  document.getElementById('campo-stock-container').style.display = 'none';
  document.getElementById('stock').disabled = true;

  if (typeof abrirSlideOver === 'function') abrirSlideOver();
};

// Intercepta el submit del slide-over solo en modo granel; el alta/edicion de
// producto normal sigue con su POST nativo.
if (formProducto) {
  formProducto.addEventListener('submit', (e) => {
    if (formProducto.dataset.modo !== 'granel') return;
    e.preventDefault();

    const inputPrecio = document.getElementById('precio');
    const articulo = formProducto.dataset.articulo;
    const monto = leerMiles(inputPrecio);

    if (!monto || parseFloat(monto) < 1) {
      if (typeof notificarError === 'function') notificarError('Ingrese un precio válido (mínimo 1).');
      inputPrecio.focus();
      return;
    }

    const boton = document.querySelector('.boton-primario');
    boton.disabled = true;

    fetch(formProducto.dataset.urlCotizacion, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': formProducto.querySelector('[name="csrfmiddlewaretoken"]').value,
      },
      body: JSON.stringify({ articulo: articulo, monto: monto }),
    })
      .then((response) => response.json())
      .then((data) => {
        if (data.ok) {
          // Refresco la celda de precio de la fila sin recargar la tabla
          const fila = contenedorTabla.querySelector(`tr.fila-granel[data-articulo="${articulo}"]`);
          if (fila) {
            const celda = fila.querySelector('.precio-valor');
            const formateado = new Intl.NumberFormat('es-AR', { maximumFractionDigits: 2 }).format(Number(monto));
            celda.innerHTML = `$ ${formateado}<span class="granel-unidad">/kg</span>`;
          }
          if (typeof cerrarSlideOver === 'function') cerrarSlideOver();
          salirModoGranel();
          if (typeof notificarExito === 'function') notificarExito('Precio actualizado correctamente');
        } else if (typeof notificarError === 'function') {
          notificarError('Error al actualizar: ' + data.error);
        }
      })
      .catch((error) => {
        console.error('Error:', error);
        if (typeof notificarError === 'function') notificarError('Error de conexión');
      })
      .finally(() => {
        boton.disabled = false;
      });
  });
}

// Hago accesibles las funciones que el HTML llama mediante "onclick"
window.prepararPanelNuevoProducto = prepararPanelNuevoProducto;