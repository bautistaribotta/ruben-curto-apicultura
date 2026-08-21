// Selector de fecha de la operación (ventas y compras).
// Por defecto la operación es de hoy y el selector está plegado: solo se ve
// "Fecha: hoy · Cambiar". Al tocarlo se despliega el input de fecha.
//
// Al elegir una fecha anterior a hoy se abre el modal de cotizaciones
// históricas: pide miel menor a 50 mm, dólar oficial (venta) y cera opérculo de aquel
// día, para guardarlos como cotizaciones de origen de la operación migrada
// desde el sistema viejo. Cancelar el modal revierte la fecha.
//
// Expone:
//   window.obtenerFechaOperacion()          -> "YYYY-MM-DD" o null
//   window.obtenerCotizacionesHistoricas()  -> {valor_dolar, valor_kilo_miel, valor_kilo_cera} o null
//   window.faltanCotizacionesHistoricas()   -> true si la fecha exige cotizaciones y no están cargadas
//   window.abrirModalCotizacionesHistoricas() -> reabre el modal (guardia previa al submit)
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
    const hintTexto = document.getElementById('fecha-hint-texto');
    const botonEditarCotiz = document.getElementById('boton-editar-cotizaciones');
    const hoy = input.dataset.hoy;
    const hintTextoOriginal = hintTexto ? hintTexto.textContent : '';

    // Fecha con la que carga la vista: hoy al crear, la de la operación al
    // editar. Volver a esa fecha no exige cotizaciones (el backend no las toca).
    const valorInicial = input.value || hoy;

    // Modal de cotizaciones históricas (presente en ventas y compras)
    const modal = document.getElementById('contenedor-modal-cotizaciones');
    const fondoModal = document.getElementById('contenedor-modal-fondo-cotizaciones');
    const fechaModal = document.getElementById('fecha-modal-cotizaciones');
    const formModal = document.getElementById('form-cotizaciones');
    const errorModal = document.getElementById('error-modal-cotizaciones');
    const botonCerrar = document.getElementById('boton-cerrar-cotizaciones');
    const botonCancelar = document.getElementById('boton-cancelar-cotizaciones');
    const inputsModal = {
        valor_kilo_miel: document.getElementById('input-cotiz-miel'),
        valor_dolar: document.getElementById('input-cotiz-dolar'),
        valor_kilo_cera: document.getElementById('input-cotiz-cera'),
    };

    // Cotizaciones confirmadas para la fecha elegida (null = sin cargar).
    // ultimosValores conserva lo tipeado para precargar el modal si se
    // reabre (útil al migrar varias operaciones de la misma época).
    let cotizaciones = null;
    let ultimosValores = null;

    function esHoy() {
        return !input.value || input.value === hoy;
    }

    // Fecha anterior a hoy y distinta a la inicial: exige cotizaciones de origen.
    // La comparación de strings "YYYY-MM-DD" respeta el orden cronológico.
    function exigeCotizaciones(valor) {
        return !!valor && valor < hoy && valor !== valorInicial;
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

        // Si la fecha actual ya no exige cotizaciones, se descartan las
        // confirmadas para no mandar valores de otro día.
        if (!exigeCotizaciones(input.value)) cotizaciones = null;

        if (hintTexto) {
            if (cotizaciones) {
                hintTexto.textContent = `Cotizaciones del ${formatearFecha(input.value)} cargadas.`;
            } else {
                hintTexto.textContent = hintTextoOriginal;
            }
        }
        if (botonEditarCotiz) botonEditarCotiz.classList.toggle('oculto', !cotizaciones);
        hint.classList.toggle('oculto', esHoy());
    }

    // ----- Modal -----

    function abrirModal() {
        if (!modal) return;
        fechaModal.textContent = formatearFecha(input.value);
        const precarga = cotizaciones || ultimosValores;
        Object.entries(inputsModal).forEach(([campo, campoInput]) => {
            // La precarga guarda los valores pelados, se reescriben con formato
            ponerValorMiles(campoInput, precarga ? precarga[campo] : '');
            campoInput.closest('.modal-cotiz__campo').classList.remove('es-invalido');
        });
        errorModal.classList.add('oculto');
        modal.classList.add('abierto');
        document.body.style.overflow = 'hidden';
        setTimeout(() => inputsModal.valor_dolar.focus(), 100);
    }

    function cerrarModal() {
        modal.classList.remove('abierto');
        document.body.style.overflow = 'auto';
    }

    // Cancelar (X, fondo, Escape o botón): la fecha vuelve a la inicial y se
    // avisa por qué, para que el usuario reintente cargando los 3 valores.
    function cancelarModal() {
        cerrarModal();
        input.value = valorInicial;
        refrescar();
        const destino = valorInicial === hoy ? 'hoy' : `al ${formatearFecha(valorInicial)}`;
        const aviso = `La fecha volvió a ${destino} porque no se cargaron las cotizaciones. ` +
            'Para registrar una operación con fecha anterior, elegí de nuevo la fecha y completá los 3 valores de ese día.';
        if (typeof notificarErrorModal === 'function') notificarErrorModal(aviso);
        else alert(aviso);
    }

    function confirmarModal() {
        const valores = {};
        let invalido = false;

        Object.entries(inputsModal).forEach(([campo, campoInput]) => {
            // Estos valores no salen por submit sino en el JSON de la operacion,
            // asi que los peleo aca antes de validarlos y guardarlos
            const crudo = leerMiles(campoInput);
            const valor = parseFloat(crudo);
            const esValido = !isNaN(valor) && valor >= 1;
            campoInput.closest('.modal-cotiz__campo').classList.toggle('es-invalido', !esValido);
            if (esValido) valores[campo] = crudo;
            else invalido = true;
        });

        errorModal.classList.toggle('oculto', !invalido);
        if (invalido) return;

        cotizaciones = valores;
        ultimosValores = valores;
        cerrarModal();
        refrescar();
    }

    if (modal) {
        botonCerrar.addEventListener('click', cancelarModal);
        botonCancelar.addEventListener('click', cancelarModal);
        fondoModal.addEventListener('click', cancelarModal);
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && modal.classList.contains('abierto')) cancelarModal();
        });
        formModal.addEventListener('submit', (e) => {
            e.preventDefault();
            confirmarModal();
        });
    }

    if (botonEditarCotiz) botonEditarCotiz.addEventListener('click', abrirModal);

    // ----- Selector de fecha -----

    toggle.addEventListener('click', () => {
        const abierto = !panel.classList.toggle('oculto');
        toggle.setAttribute('aria-expanded', abierto);
        accion.textContent = abierto ? 'Ocultar' : 'Cambiar';
        if (abierto) input.focus();
    });

    input.addEventListener('input', refrescar);
    input.addEventListener('change', () => {
        refrescar();
        // Fecha anterior a hoy recién elegida y sin cotizaciones confirmadas:
        // se piden en el momento
        if (exigeCotizaciones(input.value) && !cotizaciones) abrirModal();
    });

    botonHoy.addEventListener('click', () => {
        input.value = hoy;
        refrescar();
    });

    // Devuelve siempre el valor cargado: al crear, el backend trata la fecha de
    // hoy igual que no mandar nada; al editar, hoy es un valor nuevo legitimo.
    window.obtenerFechaOperacion = function () {
        return input.value || null;
    };

    window.obtenerCotizacionesHistoricas = function () {
        return exigeCotizaciones(input.value) ? cotizaciones : null;
    };

    window.faltanCotizacionesHistoricas = function () {
        return exigeCotizaciones(input.value) && !cotizaciones;
    };

    window.abrirModalCotizacionesHistoricas = abrirModal;

    refrescar();
});
