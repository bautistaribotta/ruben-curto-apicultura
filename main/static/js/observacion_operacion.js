// Observación opcional de la operación (ventas y compras).
// Mismo patrón plegable que el selector de fecha: colapsado muestra
// "Observación: sin nota · Agregar"; al tocarlo se despliega el textarea
// (máximo 250 caracteres, se imprime en el remito bajo "Observaciones:").
//
// Expone:
//   window.obtenerObservacion() -> texto sin espacios sobrantes ("" si no hay)
document.addEventListener('DOMContentLoaded', () => {
    const bloque = document.getElementById('cart-obs');
    if (!bloque) return;

    const toggle = document.getElementById('boton-observacion');
    const panel = document.getElementById('panel-observacion');
    const input = document.getElementById('input-observacion');
    const etiqueta = document.getElementById('obs-etiqueta');
    const accion = toggle.querySelector('.cart-obs__accion');
    const contador = document.getElementById('obs-contador');
    const MAXIMO = 250;

    // Modo edición: precarga la observación guardada de la operación
    const scriptEdicion = document.getElementById('datos-edicion');
    if (scriptEdicion) {
        const edicion = JSON.parse(scriptEdicion.textContent);
        if (edicion && edicion.observaciones) input.value = edicion.observaciones;
    }

    function textoActual() {
        return input.value.trim();
    }

    // La etiqueta plegada muestra un adelanto de la nota para verla de un
    // vistazo sin abrir el panel
    function refrescar() {
        const texto = textoActual();
        const abierto = !panel.classList.contains('oculto');

        if (texto) {
            etiqueta.textContent = texto.length > 28 ? `${texto.slice(0, 28)}…` : texto;
        } else {
            etiqueta.textContent = 'sin nota';
        }
        bloque.classList.toggle('is-con-nota', !!texto);
        accion.textContent = abierto ? 'Ocultar' : (texto ? 'Editar' : 'Agregar');
        contador.textContent = `${input.value.length}/${MAXIMO}`;
    }

    toggle.addEventListener('click', () => {
        const abierto = !panel.classList.toggle('oculto');
        toggle.setAttribute('aria-expanded', abierto);
        if (abierto) input.focus();
        refrescar();
    });

    input.addEventListener('input', refrescar);

    window.obtenerObservacion = function () {
        return textoActual();
    };

    refrescar();
});
