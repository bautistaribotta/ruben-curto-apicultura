// =============================================
//  SEPARADOR DE MILES EN LOS INPUTS DE MONTOS
//
//  Un input type="number" no acepta el punto como separador, asi que los
//  campos son type="text" y el formato lo maneja este archivo.
//
//  Dos clases:
//    .input-miles          -> enteros. "250000" se ve "250.000"
//    .input-miles-decimal  -> con centavos, notacion es-AR. "1500.5" se ve
//                             "1.500,5" y se tipea con coma
//
//  Tres funciones para usar desde afuera:
//    formatearMiles(input)              -> reformatea lo que ya hay escrito
//    ponerValorMiles(input, valorCrudo) -> escribe un numero del servidor
//                                          ("1500.50") ya formateado
//    leerMiles(input)                   -> devuelve el valor pelado
//                                          ("1500.50") para el POST o parseFloat
//
//  Los formularios que se mandan por submit normal no necesitan llamar a
//  leerMiles: hay un handler que limpia los campos antes de que salga el POST.
//  Los que arman un JSON a mano (pagos, cotizaciones) si tienen que usarlo.
// =============================================

const formateadorMiles = new Intl.NumberFormat('es-AR');

function esCampoDecimal(input) {
    return input.classList.contains('input-miles-decimal');
}

// Parte la escritura en miles y centavos usando la primera coma. Lo que sigue
// a la coma se recorta a 2 digitos, que es lo que guardan los DecimalField.
function separarDecimal(valor) {
    const coma = valor.indexOf(',');
    if (coma === -1) {
        return [valor.replace(/\D/g, ''), null];
    }
    return [
        valor.slice(0, coma).replace(/\D/g, ''),
        valor.slice(coma + 1).replace(/\D/g, '').slice(0, 2),
    ];
}

function formatearParteEntera(digitos) {
    return digitos === '' ? '' : formateadorMiles.format(Number(digitos));
}

// Deja el valor como lo espera el servidor: solo digitos en los enteros,
// punto decimal en los que llevan centavos
function leerMiles(input) {
    if (!esCampoDecimal(input)) {
        return input.value.replace(/\D/g, '');
    }

    const [entera, decimal] = separarDecimal(input.value);
    if (decimal === null || decimal === '') {
        return entera;
    }
    // Sin parte entera es "0,50": el servidor necesita el cero adelante
    return `${entera === '' ? '0' : entera}.${decimal}`;
}

function formatearMiles(input) {
    if (!esCampoDecimal(input)) {
        input.value = formatearParteEntera(input.value.replace(/\D/g, ''));
        return;
    }

    const [entera, decimal] = separarDecimal(input.value);
    if (decimal === null) {
        input.value = formatearParteEntera(entera);
        return;
    }
    // Los centavos quedan tal cual se van tipeando: si les aplicara formato,
    // una coma recien escrita ("1.500,") se borraria sola al toque siguiente
    input.value = `${entera === '' ? '0' : formatearParteEntera(entera)},${decimal}`;
}

// Para los valores que llegan del servidor, que vienen con punto decimal
function ponerValorMiles(input, valorCrudo) {
    const texto = valorCrudo === null || valorCrudo === undefined ? '' : String(valorCrudo);
    input.value = esCampoDecimal(input) ? texto.replace('.', ',') : texto;
    formatearMiles(input);
}

// Los puntos que el formato agrega o saca corren el cursor de lugar, asi que
// lo reubico contando los caracteres que el usuario realmente escribio y
// salteando los separadores de miles.
function reformatearMilesConCursor(input) {
    const utiles = esCampoDecimal(input) ? /[\d,]/ : /\d/;
    const contar = (texto) => texto.split('').filter((c) => utiles.test(c)).length;

    const escritosAIzquierda = contar(input.value.slice(0, input.selectionStart));
    formatearMiles(input);

    let posicion = 0;
    let contados = 0;
    while (posicion < input.value.length && contados < escritosAIzquierda) {
        if (utiles.test(input.value[posicion])) {
            contados++;
        }
        posicion++;
    }
    input.setSelectionRange(posicion, posicion);
}

const SELECTOR_MILES = '.input-miles, .input-miles-decimal';

// Delego en document para que tambien agarre los campos que viven dentro de
// slide-overs y modales que se arman despues de la carga
document.addEventListener('input', (evento) => {
    if (evento.target.matches && evento.target.matches(SELECTOR_MILES)) {
        reformatearMilesConCursor(evento.target);
    }
});

// Solo limpio los campos cuando el formulario realmente va a hacer el POST.
// Los modales que cancelan el submit y arman un JSON a mano (cotizaciones)
// necesitan seguir viendo el valor con formato para leerlo con leerMiles().
document.addEventListener('submit', (evento) => {
    if (evento.defaultPrevented) return;

    evento.target.querySelectorAll(SELECTOR_MILES).forEach((campo) => {
        campo.value = leerMiles(campo);
    });
});

// Los formularios de edicion llegan con el value puesto desde la vista, sin
// formato. Los paso una vez al cargar para que se vean igual que la tabla.
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll(SELECTOR_MILES).forEach((campo) => {
        ponerValorMiles(campo, campo.value);
    });
});
