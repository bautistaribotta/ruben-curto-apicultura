// =============================================
//  PERFIL DE VEHICULO
//  Un unico slide-over (#slide-over-registro) sirve para dar de alta y editar
//  los cinco tipos de dato del vehiculo (kilometraje, seguro, VTV, service y
//  observacion). Cada tipo declara que campos usa y con que accion postea; el
//  resto de los campos se ocultan y se deshabilitan para que no viajen al server.
//  El borrado usa el modal hold-to-delete compartido (paneles.js).
// =============================================

// Que campos muestra cada tipo. Los nombres coinciden con las clases .campo-<x>.
const CAMPOS_POR_TIPO = {
    km:     ['fecha', 'kilometros'],
    seguro: ['inicio', 'fin', 'costo', 'observaciones'],
    vtv:    ['inicio', 'fin', 'costo', 'observaciones'],
    servis: ['fecha', 'costo', 'observaciones'],
    obs:    ['fecha', 'texto'],
};

// Textos y acciones de cada tipo (icono, titulos y las acciones que rutea la vista).
const META_POR_TIPO = {
    km: {
        icono: 'speed', nuevo: 'nuevo_km', editar: 'editar_km', eliminar: 'eliminar_km',
        tituloNuevo: 'Agregar kilometraje', tituloEditar: 'Editar kilometraje',
        subtitulo: 'Sumá los kilómetros recorridos',
    },
    seguro: {
        icono: 'shield', nuevo: 'nuevo_seguro', editar: 'editar_seguro', eliminar: 'eliminar_seguro',
        tituloNuevo: 'Agregar seguro', tituloEditar: 'Editar seguro',
        subtitulo: 'Cargá la vigencia de la póliza',
    },
    vtv: {
        icono: 'verified', nuevo: 'nueva_vtv', editar: 'editar_vtv', eliminar: 'eliminar_vtv',
        tituloNuevo: 'Agregar VTV', tituloEditar: 'Editar VTV',
        subtitulo: 'Cargá la vigencia de la verificación',
    },
    servis: {
        icono: 'build', nuevo: 'nuevo_servis', editar: 'editar_servis', eliminar: 'eliminar_servis',
        tituloNuevo: 'Agregar service', tituloEditar: 'Editar service',
        subtitulo: 'Anotá el service y su fecha',
    },
    obs: {
        icono: 'sticky_note_2', nuevo: 'nueva_obs', editar: 'editar_obs', eliminar: 'eliminar_obs',
        tituloNuevo: 'Agregar observación', tituloEditar: 'Editar observación',
        subtitulo: 'Dejá una nota sobre el vehículo',
    },
};

function hoyISO() {
    return new Date().toISOString().split('T')[0];
}

// Muestra los campos del tipo pedido y deshabilita el resto para que no posteen.
function configurarCampos(tipo) {
    const usados = CAMPOS_POR_TIPO[tipo];
    document.querySelectorAll('#form-registro .campo').forEach((grupo) => {
        const nombre = grupo.className.match(/campo-(\w+)/)[1];
        const activo = usados.includes(nombre);
        grupo.hidden = !activo;
        grupo.querySelectorAll('input, textarea').forEach((control) => {
            control.disabled = !activo;
            control.required = activo && nombre !== 'costo' && nombre !== 'observaciones';
        });
    });
}

function abrirFormularioNuevo(tipo) {
    const meta = META_POR_TIPO[tipo];
    const form = document.getElementById('form-registro');
    form.reset();

    document.getElementById('registro-accion').value = meta.nuevo;
    document.getElementById('registro-id').value = '';
    document.getElementById('registro-icono').textContent = meta.icono;
    document.getElementById('registro-titulo').textContent = meta.tituloNuevo;
    document.getElementById('registro-subtitulo').textContent = meta.subtitulo;

    configurarCampos(tipo);

    // Fechas por defecto en hoy para no tipearlas cada vez
    const hoy = hoyISO();
    ['fecha', 'inicio'].forEach((campo) => {
        const control = document.getElementById('campo-' + campo);
        if (control && !control.disabled) control.value = hoy;
    });

    abrirSlideOver('slide-over-registro');
}

function abrirFormularioEditar(tipo, boton) {
    const meta = META_POR_TIPO[tipo];
    const form = document.getElementById('form-registro');
    form.reset();

    document.getElementById('registro-accion').value = meta.editar;
    document.getElementById('registro-id').value = boton.dataset.id;
    document.getElementById('registro-icono').textContent = meta.icono;
    document.getElementById('registro-titulo').textContent = meta.tituloEditar;
    document.getElementById('registro-subtitulo').textContent = meta.subtitulo;

    configurarCampos(tipo);

    // Relleno cada campo visible con lo que trae el boton en sus data-*
    CAMPOS_POR_TIPO[tipo].forEach((campo) => {
        const control = document.getElementById('campo-' + campo);
        if (control) control.value = boton.dataset[campo] || '';
    });

    abrirSlideOver('slide-over-registro');
}

function abrirEliminar(tipo, boton) {
    document.getElementById('accion-eliminar').value = META_POR_TIPO[tipo].eliminar;
    document.getElementById('id-eliminar').value = boton.dataset.id;
    document.getElementById('texto-eliminar').innerHTML =
        `¿Seguro que querés eliminar <b>${boton.dataset.descripcion}</b>? Esta acción no se puede deshacer.`;
    abrirPanelEliminar();
}
