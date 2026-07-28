// Al elegir el destino de un reparto, completa el valor del viaje con la tarifa
// del catalogo. Lo usan los dos formularios: el alta (mercado_libre.html) y la
// edicion (informacion_viaje_reparto.html).
//
// El monto queda editable a proposito: la tarifa es la propuesta, pero un reparto
// puntual puede haberse cobrado distinto y el viaje guarda su propia copia.
//
// El select declara a que input escribe con data-valor-objetivo="id-del-input" y
// cada opcion trae su tarifa en data-valor.
document.addEventListener('change', (evento) => {
    const select = evento.target.closest('select[data-valor-objetivo]');
    if (!select) return;

    const input = document.getElementById(select.dataset.valorObjetivo);
    const opcion = select.selectedOptions[0];
    if (!input || !opcion || !opcion.dataset.valor) return;

    // La tarifa viene pelada del data-valor, la muestro con separador de miles
    ponerValorMiles(input, opcion.dataset.valor);
});
