// =============================================
//  LÓGICA COMPARTIDA DE MODALES DE OPERACIÓN
//  Cancelar operación y registrar pago.
//  Se usa tanto en informacion_operacion como en informacion_clientes.
// =============================================

// Formateador de moneda en formato argentino (ej: 1.234.567,50)
const formatoMonedaOperacion = new Intl.NumberFormat('es-AR', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
});

// Función auxiliar para obtener el CSRF token
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// =============================================
//  MODAL CANCELAR OPERACIÓN
// =============================================

function abrirModalCancelarOperacion(id, tipo) {
    const modal = document.getElementById('contenedor-modal-cancelar');
    const btnConfirmar = document.getElementById('boton-confirmar-cancelar');
    const textoConfirmacion = document.getElementById('texto-confirmacion-cancelar');
    const titulo = document.getElementById('titulo-modal-cancelar');
    const spanBtn = btnConfirmar.querySelector('span');

    const esCompra = tipo === 'compra';

    // Adaptamos textos segun el tipo: en compra se quita stock, en venta se devuelve
    if (titulo) {
        titulo.innerText = esCompra ? 'Confirmar eliminación' : 'Confirmar cancelación';
    }

    if (esCompra) {
        textoConfirmacion.innerHTML = `¿Seguro que quiere eliminar la compra <b>#${id}</b>? El stock que agrego sera quitado del inventario automaticamente`;
    } else {
        textoConfirmacion.innerHTML = `¿Seguro que quiere cancelar la operacion <b>#${id}</b>? Los productos seran devueltos al stock automaticamente`;
    }

    if (spanBtn) {
        spanBtn.innerText = esCompra ? 'Sí, eliminar' : 'Sí, cancelar';
        // Reseteo el texto original para que el "mantener presionado" restaure el correcto
        delete btnConfirmar.dataset.textoOriginal;
    }

    // Guardamos el ID en el botón para saber qué operación cancelar
    btnConfirmar.setAttribute('data-id', id);

    modal.classList.add('abierto');
    document.body.style.overflow = 'hidden';
}

function cerrarModalCancelarOperacion() {
    const modal = document.getElementById('contenedor-modal-cancelar');
    const btnConfirmar = document.getElementById('boton-confirmar-cancelar');

    modal.classList.remove('abierto');
    document.body.style.overflow = 'auto';

    // Limpiamos el estado del botón
    btnConfirmar.classList.remove('manteniendo');
    const span = btnConfirmar.querySelector('span');
    if (span && btnConfirmar.dataset.textoOriginal) {
        span.innerText = btnConfirmar.dataset.textoOriginal;
    }
}

// Lógica de "mantener presionado" para confirmar la cancelación
document.addEventListener('DOMContentLoaded', () => {
    const btnConfirmarCancelar = document.getElementById('boton-confirmar-cancelar');
    if (btnConfirmarCancelar) {
        let timeoutId;

        const startHold = (e) => {
            if (e.type === 'mousedown' && e.button !== 0) return;
            if (e.type === 'touchstart') e.preventDefault();

            btnConfirmarCancelar.classList.add('manteniendo');
            const span = btnConfirmarCancelar.querySelector('span');
            if (span) {
                if (!btnConfirmarCancelar.dataset.textoOriginal) {
                    btnConfirmarCancelar.dataset.textoOriginal = span.innerText;
                }
                span.innerText = "Mantenga presionado...";
            }

            timeoutId = setTimeout(() => {
                const id = btnConfirmarCancelar.getAttribute('data-id');
                ejecutarCancelacionOperacion(id);
            }, 2000); // 2 segundos
        };

        const cancelHold = () => {
            btnConfirmarCancelar.classList.remove('manteniendo');
            const span = btnConfirmarCancelar.querySelector('span');
            if (span && btnConfirmarCancelar.dataset.textoOriginal) {
                span.innerText = btnConfirmarCancelar.dataset.textoOriginal;
            }
            clearTimeout(timeoutId);
        };

        btnConfirmarCancelar.addEventListener('mousedown', startHold);
        btnConfirmarCancelar.addEventListener('mouseup', cancelHold);
        btnConfirmarCancelar.addEventListener('mouseleave', cancelHold);
        btnConfirmarCancelar.addEventListener('touchstart', startHold, {passive: false});
        btnConfirmarCancelar.addEventListener('touchend', cancelHold);
        btnConfirmarCancelar.addEventListener('touchcancel', cancelHold);
    }
});

async function ejecutarCancelacionOperacion(id) {
    try {
        const response = await fetch(`/cancelar_operacion/${id}/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCookie('csrftoken'),
                'Content-Type': 'application/json'
            }
        });

        if (response.ok) {
            window.location.reload();
        } else {
            const data = await response.json().catch(() => ({}));
            notificarErrorModal(data.error || "Hubo un error al cancelar la operación.");
            cerrarModalCancelarOperacion();
        }
    } catch (error) {
        console.error("Error:", error);
        notificarErrorModal("Ocurrió un error inesperado al cancelar la operación.");
        cerrarModalCancelarOperacion();
    }
}

// =============================================
//  MODAL AÑADIR PAGO
// =============================================

function abrirModalPago(idOperacion, montoTotalStr, totalPagadoStr) {
    // Reemplazamos coma por punto para float en caso de que venga con formato regional
    const montoTotal = parseFloat(montoTotalStr.replace(',', '.')) || 0;
    const totalPagado = parseFloat(totalPagadoStr.replace(',', '.')) || 0;
    const restante = montoTotal - totalPagado;

    document.getElementById('id_operacion_pago').value = idOperacion;

    document.getElementById('titulo-modal-pago').innerHTML = `Añadir pago a la operación <b>#${idOperacion}</b>`;

    // Mostramos el restante con separador de miles
    document.getElementById('monto-restante-pago').textContent = `$${formatoMonedaOperacion.format(restante)}`;

    const inputMonto = document.getElementById('input-monto-pago');
    inputMonto.value = '';
    // Guardamos el máximo permitido (se usa en la validación). Queda sin formato porque es el value de un input numérico
    inputMonto.max = restante.toFixed(2);

    const modal = document.getElementById('contenedor-modal-pago');
    modal.classList.add('abierto');
    document.body.style.overflow = 'hidden';

    // Enfocar el input después de que se abra el modal
    setTimeout(() => {
        inputMonto.focus();
    }, 100);
}

function completarPagoTotal() {
    const inputMonto = document.getElementById('input-monto-pago');
    if (inputMonto && inputMonto.max) {
        // El max esta guardado sin formato, lo escribo con separador de miles
        ponerValorMiles(inputMonto, inputMonto.max);
        inputMonto.focus();
    }
}

function cerrarModalPago() {
    const modal = document.getElementById('contenedor-modal-pago');
    modal.classList.remove('abierto');
    document.body.style.overflow = 'auto';
}

function procesarPago() {
    const idOperacion = document.getElementById('id_operacion_pago').value;
    // El pago no sale por submit sino en un JSON armado a mano, asi que el
    // valor hay que pelarlo aca: "1.500,50" -> "1500.50"
    const monto = leerMiles(document.getElementById('input-monto-pago'));
    const maxPermitido = document.getElementById('input-monto-pago').max;

    if (!monto || isNaN(monto) || parseFloat(monto) <= 0) {
        if (typeof notificarError === 'function') notificarError("Ingrese un monto válido.");
        else alert("Ingrese un monto válido.");
        return;
    }

    // Redondeamos ambos a 2 decimales para evitar problemas de precisión float
    const montoNum = Math.round(parseFloat(monto) * 100) / 100;
    const maxNum = Math.round(parseFloat(maxPermitido) * 100) / 100;

    if (montoNum > maxNum) {
        const err = `El monto no puede superar el restante a pagar ($${formatoMonedaOperacion.format(maxNum)}).`;
        if (typeof notificarError === 'function') notificarError(err);
        else alert(err);
        return;
    }

    const btn = document.getElementById('boton-confirmar-pago');
    btn.disabled = true;
    const spanOriginal = btn.innerHTML;
    btn.innerHTML = '<span>Procesando...</span>';

    fetch(`/registrar_pago/${idOperacion}/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken')
        },
        body: JSON.stringify({ monto: monto })
    })
    .then(response => response.json())
    .then(data => {
        if(data.ok) {
            cerrarModalPago();
            window.location.reload();
        } else {
            const err = data.error || "Hubo un error al registrar el pago.";
            notificarErrorModal(err);
            btn.disabled = false;
            btn.innerHTML = spanOriginal;
        }
    })
    .catch(err => {
        console.error("Error al procesar pago:", err);
        const msg = "Error de conexión. Intente nuevamente.";
        notificarErrorModal(msg);
        btn.disabled = false;
        btn.innerHTML = spanOriginal;
    });
}
