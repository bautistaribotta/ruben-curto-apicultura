// =============================================
//  DADORA DE CARGA (alta y edicion de viajes de cereal)
//
//  Un switch decide si el viaje tuvo dadora. Cuando esta activo se muestran el
//  nombre, la forma de cobro y el valor; cuando esta apagado se ocultan y se
//  deshabilitan (asi no viajan en el POST y su validacion no bloquea el envio).
//
//  La forma de cobro (porcentaje, por tonelada o efectivo) elige cual de los inputs
//  de valor queda activo. Todos comparten el name "dadora_valor" a proposito: el
//  servidor recibe un unico valor y lo interpreta segun el tipo de cobro.
//  Deshabilitar los que no se usan es lo que evita que se manden de mas.
// =============================================

function inicializarDadoraCarga(ids) {
    const toggle = document.getElementById(ids.toggle);
    if (!toggle) return;

    const campos = document.getElementById(ids.campos);
    const nombre = document.getElementById(ids.nombre);
    const tipo = document.getElementById(ids.tipo);

    // ids.valores: { porcentaje: {grupo, input}, tonelada: {...}, efectivo: {...} }
    const valores = Object.entries(ids.valores).map(([clave, refs]) => ({
        clave,
        grupo: document.getElementById(refs.grupo),
        input: document.getElementById(refs.input),
    }));

    // La fila forma-de-cobro: el contenedor que pasa de 1 a 2 columnas
    const filaCobro = tipo.closest('.dadora-fila-cobro');

    const sincronizar = () => {
        const activa = toggle.checked;

        campos.hidden = !activa;
        campos.style.display = activa ? '' : 'none';
        nombre.disabled = !activa;
        tipo.disabled = !activa;
        nombre.required = activa;
        tipo.required = activa;

        let hayValorVisible = false;
        valores.forEach(({ clave, grupo, input }) => {
            const usado = activa && tipo.value === clave;
            grupo.hidden = !usado;
            grupo.style.display = usado ? '' : 'none';
            input.disabled = !usado;
            input.required = usado;
            if (usado) hayValorVisible = true;
        });

        // Cuando hay un input de valor visible, la fila pasa a 2 columnas;
        // cuando no, el select ocupa todo el ancho.
        if (filaCobro) {
            filaCobro.classList.toggle('dadora-fila-cobro--duo', hayValorVisible);
        }

        // Al apagar el switch dejo los campos en blanco: si el usuario habia
        // cargado una dadora y se arrepiente, el viaje no debe quedar con datos
        // sueltos que ni siquiera se ven.
        if (!activa) {
            nombre.value = '';
            tipo.value = '';
            valores.forEach(({ input }) => { input.value = ''; });
        }
    };

    toggle.addEventListener('change', sincronizar);
    tipo.addEventListener('change', sincronizar);

    // Al cerrar el slide-over se hace formulario.reset(), que devuelve el switch a su
    // valor por defecto pero no dispara 'change' ni restaura los 'hidden': sin esto los
    // campos quedaban visibles con el switch apagado. reset() ya restauro los valores
    // cuando salta este evento, asi que sincronizar solo reconcilia que se vea/envie.
    const formulario = toggle.form;
    if (formulario) {
        formulario.addEventListener('reset', () => {
            // El reset todavia no aplico los valores por defecto cuando corre el
            // listener; lo dejo para el proximo tick para leer el estado ya reseteado.
            setTimeout(sincronizar, 0);
        });
    }

    // Reconcilio el estado al cargar la pagina. Es seguro para la edicion: si el viaje
    // tiene dadora el switch viene activo y no se limpia nada; si no la tiene, los
    // campos ya estan vacios. Cubre recargas y restauraciones del navegador (bfcache).
    sincronizar();
}
