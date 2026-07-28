// Redirecciono a la vista de nueva operacion al hacer click
function irANuevaOperacion(id) {
    window.location.href = `/nueva_operacion_venta/${id}/`;
}

// Funciones para el panel de eliminar
function abrirPanelEliminarDesdePerfil(id, nombre) {
    document.getElementById('id_eliminar').value = id;
    document.getElementById('texto-confirmacion-eliminar').innerHTML = `¿Confirma que quiere eliminar al cliente <b>${nombre}</b>?`;

    document.getElementById('contenedor-panel-eliminar').classList.add('abierto');
    document.body.style.overflow = 'hidden';
}

function cerrarPanelEliminar() {
    document.getElementById('contenedor-panel-eliminar').classList.remove('abierto');
    document.body.style.overflow = 'auto';
}

// =============================================
//  MODAL DE RESUMEN DE CUENTA CORRIENTE
// =============================================

function abrirModalResumen() {
    const contenedor = document.getElementById('contenedor-modal-resumen');
    if (!contenedor) return;
    contenedor.classList.add('abierto');
    document.body.style.overflow = 'hidden';
}

function cerrarModalResumen() {
    const contenedor = document.getElementById('contenedor-modal-resumen');
    // Si el modal ya estaba cerrado no toco nada: la vista tiene otros modales y
    // devolver el scroll aca les sacaria el bloqueo mientras siguen abiertos
    if (!contenedor || !contenedor.classList.contains('abierto')) return;
    contenedor.classList.remove('abierto');
    document.body.style.overflow = 'auto';
}

document.addEventListener('DOMContentLoaded', () => {
    const boton = document.getElementById('btn-resumen-cuenta');
    const formulario = document.getElementById('form-resumen-cuenta');
    // El modal solo existe para el staff: sin el, no engancho nada
    if (!boton || !formulario) return;

    const inputDesde = document.getElementById('resumen-desde');
    const inputHasta = document.getElementById('resumen-hasta');
    const atajos = document.querySelectorAll('#resumen-atajos .rc-atajo');
    const conteo = document.getElementById('resumen-conteo');
    const botonImprimir = document.getElementById('boton-imprimir-resumen');
    const urlConteo = formulario.dataset.urlConteo;

    // Formateo a mano en vez de toISOString(): ese convierte a UTC y en Argentina
    // adelantaria un dia la fecha elegida
    const aIso = (fecha) => {
        const mes = String(fecha.getMonth() + 1).padStart(2, '0');
        const dia = String(fecha.getDate()).padStart(2, '0');
        return `${fecha.getFullYear()}-${mes}-${dia}`;
    };

    // Cortes con los que se emite un resumen en la practica: el mes en curso, el
    // mes cerrado anterior, el trimestre movil y el año en curso
    function rangoDelAtajo(periodo) {
        const hoy = new Date();
        switch (periodo) {
            case 'mes':
                return [new Date(hoy.getFullYear(), hoy.getMonth(), 1), hoy];
            case 'mes-anterior':
                return [
                    new Date(hoy.getFullYear(), hoy.getMonth() - 1, 1),
                    new Date(hoy.getFullYear(), hoy.getMonth(), 0),
                ];
            case 'trimestre':
                return [new Date(hoy.getFullYear(), hoy.getMonth() - 2, 1), hoy];
            case 'anio':
                return [new Date(hoy.getFullYear(), 0, 1), hoy];
            default:
                return [hoy, hoy];
        }
    }

    // Marco el atajo cuyo rango coincide con lo que hay en los inputs, asi el chip
    // sigue reflejando la realidad aunque el usuario toque las fechas a mano
    function sincronizarAtajos() {
        atajos.forEach((atajo) => {
            const [desde, hasta] = rangoDelAtajo(atajo.dataset.periodo);
            const coincide = inputDesde.value === aIso(desde) && inputHasta.value === aIso(hasta);
            atajo.classList.toggle('activo', coincide);
        });
    }

    function aplicarAtajo(periodo) {
        const [desde, hasta] = rangoDelAtajo(periodo);
        inputDesde.value = aIso(desde);
        inputHasta.value = aIso(hasta);
        sincronizarAtajos();
        consultarConteo();
    }

    function pintarConteo(estado, texto) {
        conteo.dataset.estado = estado;
        conteo.textContent = texto;
        // Sin movimientos no hay nada que imprimir: bloqueo la emision en vez de
        // dejar que salga una hoja en blanco
        botonImprimir.disabled = estado === 'vacio';
    }

    let temporizador;
    let peticionEnCurso;

    function consultarConteo() {
        clearTimeout(temporizador);
        if (!inputDesde.value || !inputHasta.value) {
            pintarConteo('cargando', 'Elegí un rango de fechas para ver el período.');
            botonImprimir.disabled = true;
            return;
        }

        pintarConteo('cargando', 'Buscando movimientos...');
        temporizador = setTimeout(() => {
            // Descarto la respuesta anterior si el usuario sigue cambiando fechas
            if (peticionEnCurso) peticionEnCurso.abort();
            peticionEnCurso = new AbortController();

            const parametros = new URLSearchParams({desde: inputDesde.value, hasta: inputHasta.value});
            fetch(`${urlConteo}?${parametros}`, {signal: peticionEnCurso.signal})
                .then((respuesta) => {
                    if (!respuesta.ok) throw new Error(respuesta.status);
                    return respuesta.json();
                })
                .then((datos) => {
                    if (datos.cantidad === 0) {
                        pintarConteo('vacio', 'Sin movimientos en el período elegido.');
                    } else {
                        const plural = datos.cantidad === 1 ? 'movimiento' : 'movimientos';
                        pintarConteo('ok', `${datos.cantidad} ${plural} en el período elegido.`);
                    }
                })
                .catch((error) => {
                    if (error.name === 'AbortError') return;
                    // Si falla la consulta dejo imprimir igual: el conteo es una ayuda,
                    // no un requisito para emitir el resumen
                    pintarConteo('error', 'No se pudo consultar el período. Podés imprimir igual.');
                    botonImprimir.disabled = false;
                });
        }, 300);
    }

    boton.addEventListener('click', () => {
        // Arranca en el mes en curso, que es el resumen que mas se pide
        aplicarAtajo('mes');
        abrirModalResumen();
    });

    atajos.forEach((atajo) => {
        atajo.addEventListener('click', () => aplicarAtajo(atajo.dataset.periodo));
    });

    [inputDesde, inputHasta].forEach((input) => {
        input.addEventListener('change', () => {
            sincronizarAtajos();
            consultarConteo();
        });
    });

    // El resumen sale en otra pestaña (target="_blank"), asi que cierro el modal
    // para dejar el perfil como estaba
    formulario.addEventListener('submit', () => {
        setTimeout(cerrarModalResumen, 200);
    });

    document.addEventListener('keydown', (evento) => {
        if (evento.key === 'Escape') cerrarModalResumen();
    });
});

// =============================================
//  EDICIÓN INLINE DE CLIENTE
// =============================================

document.addEventListener('DOMContentLoaded', () => {
    const btnEditar = document.getElementById('btn-editar-cliente');
    const btnCancelar = document.getElementById('btn-cancelar-edicion');
    const accionesEdicion = document.getElementById('acciones-edicion');
    const valoresVista = document.querySelectorAll('.valor-vista');
    const inputsEdicion = document.querySelectorAll('.input-edicion');
    let editando = false;

    function activarEdicion() {
        editando = true;
        // Ocultar textos, mostrar inputs
        valoresVista.forEach(el => el.style.display = 'none');
        inputsEdicion.forEach(el => el.style.display = '');
        // Mostrar botones guardar/cancelar
        accionesEdicion.style.display = '';
        // Cambiar el botón de editar a estilo activo
        btnEditar.classList.add('activo');
        // Poner borde en la tarjeta
        document.querySelector('.tarjeta-info-unica').classList.add('editando');
    }

    function desactivarEdicion() {
        editando = false;
        // Mostrar textos, ocultar inputs
        valoresVista.forEach(el => el.style.display = '');
        inputsEdicion.forEach(el => el.style.display = 'none');
        // Ocultar botones guardar/cancelar
        accionesEdicion.style.display = 'none';
        // Quitar estilo activo
        btnEditar.classList.remove('activo');
        document.querySelector('.tarjeta-info-unica').classList.remove('editando');
        // Restaurar valores originales en los inputs
        document.getElementById('form-editar-cliente').reset();

        // Al resetear el formulario, el checkbox vuelve a su estado original,
        // pero no dispara el evento 'change'. Fuerzo la actualización aquí
        // para que se remueva el atributo 'required' y desaparezca el error en rojo.
        if (typeof actualizarRequiredCuit === 'function') {
            actualizarRequiredCuit();
        }
    }

    btnEditar.addEventListener('click', () => {
        if (editando) {
            desactivarEdicion();
        } else {
            activarEdicion();
        }
    });

    btnCancelar.addEventListener('click', () => {
        desactivarEdicion();
    });

    // CUIT obligatorio si factura la producción
    const checkFactura = document.querySelector('input[name="factura"]');
    const inputCuit = document.querySelector('input[name="cuit"].input-edicion');

    function actualizarRequiredCuit() {
        if (checkFactura.checked) {
            inputCuit.required = true;
        } else {
            inputCuit.required = false;
            inputCuit.value = '';
        }
    }

    checkFactura.addEventListener('change', actualizarRequiredCuit);
    // Aplicar estado inicial
    actualizarRequiredCuit();

    // Autocapitalizar la primera letra al escribir en campos de nombre y apellido
    const inputsNombres = document.querySelectorAll('input[name="nombre"], input[name="apellido"]');
    inputsNombres.forEach(input => {
        input.addEventListener('input', (e) => {
            let valor = e.target.value;
            if (valor.length > 0) {
                e.target.value = valor.charAt(0).toUpperCase() + valor.slice(1);
            }
        });
    });

    // Lógica para mantener apretado el botón de eliminar durante 2 segundos
    const btnEliminar = document.getElementById('boton-confirmar-eliminar');
    if (btnEliminar) {
        let timeoutId;

        const startHold = (e) => {
            if (e.type === 'mousedown' && e.button !== 0) return;
            if (e.type === 'touchstart') e.preventDefault();

            btnEliminar.classList.add('manteniendo');
            const span = btnEliminar.querySelector('span');
            if (span) {
                if (!btnEliminar.dataset.textoOriginal) {
                    btnEliminar.dataset.textoOriginal = span.innerText;
                }
                span.innerText = "Mantenga presionado...";
            }

            timeoutId = setTimeout(() => {
                const form = document.getElementById('formulario-eliminar');
                if (form) form.submit();
            }, 2000); // 2 segundos
        };

        const cancelHold = () => {
            btnEliminar.classList.remove('manteniendo');
            const span = btnEliminar.querySelector('span');
            if (span && btnEliminar.dataset.textoOriginal) {
                span.innerText = btnEliminar.dataset.textoOriginal;
            }
            clearTimeout(timeoutId);
        };

        btnEliminar.addEventListener('mousedown', startHold);
        btnEliminar.addEventListener('mouseup', cancelHold);
        btnEliminar.addEventListener('mouseleave', cancelHold);
        btnEliminar.addEventListener('touchstart', startHold, {passive: false});
        btnEliminar.addEventListener('touchend', cancelHold);
        btnEliminar.addEventListener('touchcancel', cancelHold);
    }

    // Permitir solo números en los campos Teléfono y CUIT
    const inputTelefono = document.querySelector('input[name="telefono"].input-edicion');
    if (inputTelefono) {
        inputTelefono.addEventListener('input', (e) => {
            e.target.value = e.target.value.replace(/\D/g, '');
        });
    }

    if (inputCuit) {
        inputCuit.addEventListener('input', (e) => {
            e.target.value = e.target.value.replace(/\D/g, '');

            // Si el usuario escribe algo y el switch de factura está apagado, lo enciendo automáticamente
            if (e.target.value.length > 0 && checkFactura && !checkFactura.checked) {
                checkFactura.checked = true;
                // Actualizo el atributo 'required' llamando a la función
                actualizarRequiredCuit();
            }
        });
    }
});
