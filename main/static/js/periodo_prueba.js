// Aviso y bloqueo por fin del periodo de prueba.
//
// Es un bloqueo solo del front: a partir de AVISO_DESDE se muestra un modal
// que se puede cerrar 6 horas con "Entendido"; a partir de BLOQUEO_DESDE el
// boton desaparece y la aplicacion queda tapada. El backend sigue vivo.
//
// Las fechas llevan el desfase de Argentina (-03:00, sin horario de verano)
// para que el momento no dependa del reloj ni de la zona horaria del equipo.
(function () {
    const AVISO_DESDE = new Date('2026-09-23T08:00:00-03:00').getTime();
    const BLOQUEO_DESDE = new Date('2026-09-25T10:00:00-03:00').getTime();
    const HORAS_OCULTO = 6;
    const CLAVE_OCULTO_HASTA = 'periodoPruebaOcultoHasta';

    function leerOcultoHasta() {
        try {
            return Number(localStorage.getItem(CLAVE_OCULTO_HASTA)) || 0;
        } catch (e) {
            return 0;
        }
    }

    function guardarOcultoHasta(momento) {
        try {
            localStorage.setItem(CLAVE_OCULTO_HASTA, String(momento));
        } catch (e) {
            // Sin almacenamiento el modal simplemente vuelve en la proxima carga
        }
    }

    /* inert saca del foco y del lector de pantalla todo lo que queda detras:
       el overlay tapa los clicks pero no impide llegar con Tab a los formularios. */
    function bloquearFondo(bloquear) {
        ['barra-lateral', 'mobile-top-bar', 'contenido-principal'].forEach(function (id) {
            const elemento = document.getElementById(id);
            if (!elemento) return;
            if (bloquear) elemento.setAttribute('inert', '');
            else elemento.removeAttribute('inert');
        });
    }

    function abrir(bloqueado) {
        const contenedor = document.getElementById('contenedor-modal-prueba');
        if (!contenedor) return;
        contenedor.classList.toggle('bloqueado', bloqueado);
        contenedor.classList.add('abierto');
        document.body.style.overflow = 'hidden';
        bloquearFondo(true);
    }

    function cerrar() {
        const contenedor = document.getElementById('contenedor-modal-prueba');
        if (!contenedor) return;
        contenedor.classList.remove('abierto');
        document.body.style.overflow = 'auto';
        bloquearFondo(false);
    }

    function evaluar() {
        const ahora = Date.now();
        if (ahora >= BLOQUEO_DESDE) {
            abrir(true);
        } else if (ahora >= AVISO_DESDE && ahora >= leerOcultoHasta()) {
            abrir(false);
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        const boton = document.getElementById('boton-entendido-prueba');
        if (boton) {
            boton.addEventListener('click', function () {
                guardarOcultoHasta(Date.now() + HORAS_OCULTO * 60 * 60 * 1000);
                cerrar();
            });
        }
        evaluar();
        // Una pestaña que quedo abierta tambien tiene que pasar al bloqueo
        setInterval(evaluar, 60 * 1000);
    });
})();
