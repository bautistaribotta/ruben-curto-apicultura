// Selector de fecha de la operación (ventas y compras).
// Por defecto la operación es de hoy y el selector está plegado: solo se ve
// "Fecha: hoy · Cambiar". Al tocarlo se despliega el input de fecha.
// Expone window.obtenerFechaOperacion() -> "YYYY-MM-DD" o null si es de hoy.
document.addEventListener('DOMContentLoaded', () => {
    const bloque = document.getElementById('cart-fecha');
    if (!bloque) return;

    const toggle = document.getElementById('boton-cambiar-fecha');
    const panel = document.getElementById('panel-fecha');
    const input = document.getElementById('input-fecha-operacion');
    const etiqueta = document.getElementById('fecha-etiqueta');
    const accion = toggle.querySelector('.cart-fecha__accion');
    const botonHoy = document.getElementById('boton-fecha-hoy');
    const hint = document.getElementById('fecha-hint');
    const hoy = input.dataset.hoy;

    function esHoy() {
        return !input.value || input.value === hoy;
    }

    // "YYYY-MM-DD" -> "DD/MM/YYYY" para la etiqueta plegada
    function formatearFecha(valor) {
        const [anio, mes, dia] = valor.split('-');
        return `${dia}/${mes}/${anio}`;
    }

    function refrescar() {
        etiqueta.textContent = esHoy() ? 'hoy' : formatearFecha(input.value);
        bloque.classList.toggle('is-cambiada', !esHoy());
        botonHoy.classList.toggle('oculto', esHoy());
        hint.classList.toggle('oculto', esHoy());
    }

    toggle.addEventListener('click', () => {
        const abierto = !panel.classList.toggle('oculto');
        toggle.setAttribute('aria-expanded', abierto);
        accion.textContent = abierto ? 'Ocultar' : 'Cambiar';
        if (abierto) input.focus();
    });

    input.addEventListener('input', refrescar);
    input.addEventListener('change', refrescar);

    botonHoy.addEventListener('click', () => {
        input.value = hoy;
        refrescar();
    });

    // Devuelve siempre el valor cargado: al crear, el backend trata la fecha de
    // hoy igual que no mandar nada; al editar, hoy es un valor nuevo legitimo.
    window.obtenerFechaOperacion = function () {
        return input.value || null;
    };

    refrescar();
});
