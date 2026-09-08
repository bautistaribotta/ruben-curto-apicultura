from datetime import date, timedelta
from decimal import Decimal

from django.db import models
from django.db.models import (Sum, F, Subquery, OuterRef, Exists, DecimalField, IntegerField,
                              DateField, Value, Q)
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.functional import cached_property


class Producto(models.Model):
    categorias = [
        ("Miel", "Miel"),
        ("Alimento", "Alimento"),
        ("Cera", "Cera"),
        ("Madera", "Madera"),
        ("Estampado", "Estampado"),
        ("Insumos", "Insumos"),
        ("Medicamentos", "Medicamentos"),
        ("Tambores Vacios", "Tambores Vacios"),
        ("Otros", "Otros"),
    ]
    nombre = models.CharField(max_length=50, unique=True)
    categoria = models.CharField(max_length=50, choices=categorias, null=True, blank=True)
    precio = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    cantidad = models.PositiveIntegerField(default=0)
    cantidad_vendida = models.PositiveIntegerField(default=0)
    cantidad_comprada = models.PositiveIntegerField(default=0)
    activo = models.BooleanField(default=True)
    """
    Marca los productos que se muestran en el tablero de inicio. Es un dato de
    cada base, no del codigo: asi cada instalacion elige que destacar sin que la
    plantilla dependa de ids ni de nombres, que cambian de una base a otra.
    """
    mostrar_en_inicio = models.BooleanField(default=False)
    """
        En sistemas comerciales, es mejor usar un campo 'activo' en lugar de borrar
        productos físicamente. Si borro un producto, podría perder el historial de ventas.
        Al usar 'activo=False', el producto deja de mostrarse en la interfaz pero los registros históricos
        en 'detalle_operaciones' permanecen intactos
    """

    # Obligo a Django a nombrar la tabla como "productos"
    class Meta:
        db_table = "productos"

    def __str__(self):
        return self.nombre


class Cliente(models.Model):
    nombre = models.CharField(max_length=50)
    apellido = models.CharField(max_length=50, null=True, blank=True)
    telefono = models.CharField(max_length=20, null=True, blank=True)
    localidad = models.CharField(max_length=50, null=True, blank=True)
    direccion = models.CharField(max_length=100, null=True, blank=True)
    factura_produccion = models.BooleanField(default=False)
    cuit = models.CharField(max_length=15, null=True, blank=True)
    activo = models.BooleanField(default=True)

    # Obligo a Django a nombrar la tabla como "clientes"
    class Meta:
        db_table = "clientes"

    def __str__(self):
        return f"{self.nombre} {self.apellido}"


class OperacionQuerySet(models.QuerySet):
    def con_totales(self):
        """
        Anota el monto total (suma de detalles) y el total pagado en una sola query,
        evitando el N+1 que generan las properties monto_total/total_pagado al iterar
        sobre un listado. Uso subqueries separadas para no sufrir el fan-out que
        multiplicaria los montos al combinar dos agregaciones por JOIN.
        """
        monto_detalles = (
            DetalleOperacion.objects.filter(operacion=OuterRef("pk"))
            .values("operacion")
            .annotate(total=Sum(F("cantidad") * F("precio_unitario")))
            .values("total")
        )
        monto_pagos = (
            Pago.objects.filter(operacion=OuterRef("pk"))
            .values("operacion")
            .annotate(total=Sum("monto"))
            .values("total")
        )
        return self.annotate(
            _monto_total_anotado=Coalesce(
                Subquery(monto_detalles, output_field=DecimalField()),
                Value(0),
                output_field=DecimalField(),
            ),
            _total_pagado_anotado=Coalesce(
                Subquery(monto_pagos, output_field=DecimalField()),
                Value(0),
                output_field=DecimalField(),
            ),
        )


class Operacion(models.Model):
    TIPO_OPERACION = [
        ("compra", "Compra"),
        ("venta", "Venta"),
    ]

    objects = OperacionQuerySet.as_manager()

    # Como la tabla viaje esta definida mas abajo, coloco el nombre entre comillas para que Django la lea antes
    viaje = models.ForeignKey("Viaje", on_delete=models.SET_NULL, null=True,
                              blank=True, related_name="operaciones", db_column="id_viaje")
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, db_column="id_cliente")
    # default y no auto_now_add para poder cargar operaciones viejas con fecha propia
    fecha = models.DateTimeField(default=timezone.now)
    activa = models.BooleanField(default=True)
    tipo_operacion = models.CharField(max_length=10, choices=TIPO_OPERACION)
    valor_dolar = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    valor_kilo_miel = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    valor_kilo_cera = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    observaciones = models.CharField(max_length=250, blank=True, default="")

    # Obligo a Django a nombrar la tabla como "operaciones"
    class Meta:
        db_table = "operaciones"
        verbose_name_plural = "Operaciones"

    @property
    def monto_total(self):
        """
        Si el queryset vino anotado con con_totales(), uso el valor ya calculado
        para no disparar una query por cada operacion del listado.
        """
        if hasattr(self, "_monto_total_anotado"):
            return self._monto_total_anotado or 0
        resultado = self.detalleoperacion_set.aggregate(
            total=Sum(F('cantidad') * F('precio_unitario'))
        )['total']
        return resultado if resultado is not None else 0

    @property
    def total_pagado(self):
        if hasattr(self, "_total_pagado_anotado"):
            return self._total_pagado_anotado or 0
        return self.pago_set.aggregate(total=Sum('monto'))['total'] or 0

    @property
    def estado_pago(self):
        if not self.activa:
            return "Cancelada"

        pagado = self.total_pagado

        if pagado == 0:
            return "Debe"
        elif pagado >= self.monto_total:
            return "Pagada"
        else:
            return "Pago Parcial"

    def __str__(self):
        return f"Operación {self.id} - {self.cliente}"


class DetalleOperacion(models.Model):
    operacion = models.ForeignKey(Operacion, on_delete=models.CASCADE, db_column="id_operacion")
    """
    Una linea de la operacion apunta a un producto envasado (venta por unidad) O a un
    articulo de cotizaciones (venta/compra a granel en kilos), nunca a los dos a la vez.
    La exclusion mutua la garantiza el CheckConstraint de abajo.
    """
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, db_column="id_producto",
                                 null=True, blank=True)
    cotizacion = models.ForeignKey("ProductoPorKg", on_delete=models.PROTECT, db_column="id_cotizacion",
                                   null=True, blank=True)
    cantidad = models.DecimalField(max_digits=10, decimal_places=2)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)

    # Obligo a Django a nombrar la tabla como "detalle_operaciones"
    class Meta:
        db_table = "detalle_operaciones"
        # Sintaxis moderna para asegurar que un producto no se repita en la misma operación
        constraints = [
            models.UniqueConstraint(
                fields=["operacion", "producto"], name="unique_operacion_producto"
            ),
            models.UniqueConstraint(
                fields=["operacion", "cotizacion"], name="unique_operacion_cotizacion"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(producto__isnull=False, cotizacion__isnull=True)
                    | models.Q(producto__isnull=True, cotizacion__isnull=False)
                ),
                name="detalle_producto_o_cotizacion",
            ),
        ]

    @property
    def es_granel(self):
        return self.cotizacion_id is not None

    @property
    def nombre_item(self):
        """
        Nombre unico para mostrar en listados, remito y detalle de operacion,
        sin que cada template tenga que ramificar entre producto y cotizacion
        """
        if self.es_granel:
            return f"{self.cotizacion.articulo} (por kg)"
        return self.producto.nombre

    def __str__(self):
        return f"{self.cantidad} de {self.nombre_item} (Op: {self.operacion.id})"


class Pago(models.Model):
    operacion = models.ForeignKey(Operacion, on_delete=models.CASCADE, db_column="id_operacion")
    """
    default (y no auto_now_add) para que el pago automatico de una operacion
    "contado" con fecha vieja pueda llevar esa misma fecha
    """
    fecha = models.DateTimeField(default=timezone.now)
    monto = models.DecimalField(max_digits=15, decimal_places=2)

    class Meta:
        db_table = "pagos"
        verbose_name_plural = "Pagos"

    def __str__(self):
        return f"Pago de la operacion: {self.operacion}"


class ProductoPorKg(models.Model):
    """
    Producto que se vende pesado, no por unidad. Comparte las categorias con
    Producto: la diferencia con esa tabla es la unidad de venta (kilos con
    decimales en vez de unidades enteras), no el rubro.

    Los cinco articulos de ARTICULOS_COTIZACION son los historicos de miel y
    cera: su precio y su stock se gobiernan desde el tablero de cotizaciones y
    desde las operaciones, asi que en el inventario se muestran de solo lectura.
    El resto se administra como cualquier producto (alta, edicion, baja y ajuste
    de stock desde la pantalla de productos).
    """
    ARTICULOS_COTIZACION = (
        "Miel menor a 34 mm",
        "Miel menor a 50 mm",
        "Miel mayor a 50 mm",
        "Cera Operculo",
        "Cera Recupero",
    )

    articulo = models.CharField(max_length=30, unique=True)
    categoria = models.CharField(max_length=50, choices=Producto.categorias, null=True, blank=True)
    monto = models.PositiveIntegerField(default=1)
    """
    Kilos disponibles a granel del articulo. Uso Decimal (no Float) para evitar
    ruido de precision al acumular pesadas fraccionadas, igual que DetalleOperacion
    """
    cantidad = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    activo = models.BooleanField(default=True)
    # Ver Producto.mostrar_en_inicio: mismo criterio para los que se venden por kilo
    mostrar_en_inicio = models.BooleanField(default=False)

    class Meta:
        db_table = "productos_por_kg"
        verbose_name_plural = "Productos por kg"

    @property
    def es_cotizacion(self):
        # Miel y cera historicas: el inventario no las edita ni las da de baja
        return self.articulo in self.ARTICULOS_COTIZACION

    def __str__(self):
        return f"Cotizacion {self.articulo}: {self.monto}"


class Empleado(models.Model):
    nombre = models.CharField(max_length=25)
    apellido = models.CharField(max_length=25)
    sueldo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    """
    Dia desde el que arranca a contar la cuenta corriente (saldo en 0). Se fija
    solo la primera vez que se carga un sueldo; antes de ese dia no se muestran
    sueldos ni se cuentan pagos. Null mientras el empleado no tenga cuenta.
    """
    inicio_cuenta = models.DateField(null=True, blank=True)
    """
    Fecha unica de vencimiento del carnet de conducir. Null mientras no se
    cargue: el perfil ofrece un boton para darla de alta y despues editarla.
    """
    vencimiento_carnet = models.DateField(null=True, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "empleados"
        verbose_name_plural = "Empleados"
        constraints = [
            models.UniqueConstraint(
                fields=["nombre", "apellido"],
                name="unique_nombre_apellido_empleado"
            )
        ]

    @property
    def total_viajes(self):
        """
        Cantidad de viajes activos del empleado, sumando los tres tipos de viaje
        (miel/cera, reparto y cereal). Un viaje cuenta como uno, sin importar
        cuantos destinos tenga. Si el queryset vino anotado con _num_viajes
        (ver obtener_empleados_activos) reutilizo ese valor para evitar una
        query por fila en el listado de flota.
        """
        if hasattr(self, "_num_viajes"):
            return self._num_viajes
        return (
            self.viaje_set.filter(activo=True).count()
            + self.viajereparto_set.filter(activo=True).count()
            + self.viajecereal_set.filter(activo=True).count()
        )

    def __str__(self):
        return f"Empleado: {self.nombre} {self.apellido}"


class PagosEmpleados(models.Model):
    """
    De donde salio el pago. "manual" es el pago comun que se carga a mano desde
    el perfil; "devolucion" es el que nace solo cuando un chofer se queda con
    parte del sobrante de la caja de un viaje de miel/cera (ver
    Viaje.registrar_devolucion en services). El origen no cambia al editar el
    pago, asi la cuenta corriente lo puede seguir distinguiendo visualmente
    aunque se le corrija el monto desde cualquiera de los dos lados.
    """
    ORIGEN_MANUAL = "manual"
    ORIGEN_DEVOLUCION = "devolucion"
    ORIGEN_CHOICES = [
        (ORIGEN_MANUAL, "Manual"),
        (ORIGEN_DEVOLUCION, "Devolución de caja"),
    ]

    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE, db_column="id_empleado")
    fecha = models.DateField(default=timezone.now)
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    observaciones = models.CharField(max_length=250, blank=True, default="")
    origen = models.CharField(max_length=15, choices=ORIGEN_CHOICES, default=ORIGEN_MANUAL)

    class Meta:
        db_table = "pagos_empleados"
        verbose_name_plural = "Pagos de Empleados"

    def __str__(self):
        return f"Pago de {self.monto} a {self.empleado} el {self.fecha}"


class Vehiculo(models.Model):
    nombre = models.CharField(max_length=30)
    patente = models.CharField(max_length=7, unique=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "vehiculos"

    @property
    def total_viajes(self):
        """
        Suma los tres tipos de viaje activos (miel/cera, reparto y cereal),
        igual que en Empleado.
        """
        if hasattr(self, "_num_viajes"):
            return self._num_viajes
        return (
            self.viaje_set.filter(activo=True).count()
            + self.viajereparto_set.filter(activo=True).count()
            + self.viajecereal_set.filter(activo=True).count()
        )

    @property
    def kilometraje_actual(self):
        """Kilometraje actual del vehiculo: la ultima lectura de odometro cargada.

        El odometro se guarda como lecturas absolutas que se van pisando: el valor
        vigente es el de la lectura mas reciente, no una suma. Los registros vienen
        ordenados del mas nuevo al mas viejo, asi que el primero es la lectura
        actual. Sin lecturas todavia, es cero.
        """
        ultimo = self.registros_km.first()
        return ultimo.kilometros if ultimo else Decimal("0")

    @property
    def ultima_actualizacion_km(self):
        """Fecha de la ultima actualizacion de kilometraje, o None si nunca.

        Es el dato que el usuario quiere recordar: cuando se actualizo el odometro
        por ultima vez. Los registros vienen ordenados del mas nuevo al mas viejo,
        asi que el primero marca la ultima actualizacion.
        """
        ultimo = self.registros_km.first()
        return ultimo.fecha if ultimo else None

    def __str__(self):
        return f"Vehiculo {self.nombre} ({self.patente})"


class RegistroKilometraje(models.Model):
    """Una lectura de odometro de un vehiculo: cuantos km marca y en que fecha.

    El odometro se registra como lecturas absolutas: cada vez que se actualiza se
    guarda el numero que marca el tablero en esa fecha, sin que el usuario calcule
    diferencias. El kilometraje actual del vehiculo es la ultima lectura (ver
    Vehiculo.kilometraje_actual) y cada actualizacion queda en el historial, de
    modo que se ve como fue subiendo con el tiempo. Corregir es editar o borrar
    una lectura.
    """
    vehiculo = models.ForeignKey(Vehiculo, on_delete=models.CASCADE, related_name="registros_km",
                                 db_column="id_vehiculo")
    """
    default y no auto_now_add: la lectura se anota cuando se puede, y la fecha que
    vale es la del dia en que el odometro marcaba ese numero, no la de la carga
    """
    fecha = models.DateField(default=timezone.localdate)
    kilometros = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = "registros_kilometraje"
        verbose_name = "Registro de kilometraje"
        verbose_name_plural = "Registros de kilometraje"
        # Del mas nuevo al mas viejo; el id desempata los del mismo dia
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"{self.kilometros} km el {self.fecha:%d/%m/%Y} ({self.vehiculo})"


class Seguro(models.Model):
    """Poliza de seguro de un vehiculo, con su vigencia de inicio a fin.

    Un vehiculo tiene varias a lo largo del tiempo (relacion uno a muchos):
    renovar el seguro es guardar una poliza nueva, no editar la vieja, para que
    quede el historial completo de cobertura. El costo y las observaciones son
    opcionales; las dos fechas de vigencia no.
    """
    vehiculo = models.ForeignKey(Vehiculo, on_delete=models.CASCADE, related_name="seguros",
                                 db_column="id_vehiculo")
    inicio = models.DateField()
    fin = models.DateField()
    costo = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    observaciones = models.CharField(max_length=200, null=True, blank=True)

    class Meta:
        db_table = "seguros"
        verbose_name = "Seguro"
        verbose_name_plural = "Seguros"
        # Del vencimiento mas nuevo al mas viejo; el id desempata
        ordering = ["-fin", "-id"]

    @property
    def vencido(self):
        return self.fin < timezone.localdate()

    def __str__(self):
        return f"Seguro de {self.vehiculo} hasta {self.fin:%d/%m/%Y}"


class VTV(models.Model):
    """Verificacion tecnica vehicular, con su vigencia de inicio a fin.

    Igual que el seguro: un vehiculo acumula varias VTV a lo largo del tiempo
    (uno a muchos) y cada nueva verificacion es un registro aparte, no una
    edicion de la anterior. Costo y observaciones opcionales; fechas obligatorias.
    """
    vehiculo = models.ForeignKey(Vehiculo, on_delete=models.CASCADE, related_name="vtvs",
                                 db_column="id_vehiculo")
    inicio = models.DateField()
    fin = models.DateField()
    costo = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    observaciones = models.CharField(max_length=200, null=True, blank=True)

    class Meta:
        db_table = "vtv"
        verbose_name = "VTV"
        verbose_name_plural = "VTV"
        ordering = ["-fin", "-id"]

    @property
    def vencido(self):
        return self.fin < timezone.localdate()

    def __str__(self):
        return f"VTV de {self.vehiculo} hasta {self.fin:%d/%m/%Y}"


class Servis(models.Model):
    """Service de mantenimiento de un vehiculo, en una fecha puntual.

    Un vehiculo tiene muchos services a lo largo de su vida (uno a muchos), cada
    uno en su fecha. A diferencia del seguro y la VTV, un service no tiene
    vigencia: es un hecho de un dia. Costo y observaciones opcionales.
    """
    vehiculo = models.ForeignKey(Vehiculo, on_delete=models.CASCADE, related_name="servicios",
                                 db_column="id_vehiculo")
    fecha = models.DateField()
    costo = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    observaciones = models.CharField(max_length=200, null=True, blank=True)

    class Meta:
        db_table = "servicios"
        verbose_name = "Servis"
        verbose_name_plural = "Servicios"
        # Del mas nuevo al mas viejo; el id desempata los del mismo dia
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"Servis de {self.vehiculo} el {self.fecha:%d/%m/%Y}"


class ObservacionVehiculo(models.Model):
    """Nota libre sobre un vehiculo, con su fecha.

    Un vehiculo acumula varias a lo largo del tiempo (uno a muchos): es un cuaderno
    de anotaciones donde el usuario escribe lo que quiera sobre el vehiculo, sin un
    formato fijo. La fecha ubica cada nota; el texto es obligatorio, porque una
    observacion vacia no anota nada.
    """
    vehiculo = models.ForeignKey(Vehiculo, on_delete=models.CASCADE, related_name="observaciones",
                                 db_column="id_vehiculo")
    # default y no auto_now_add: la nota puede referirse a algo de otro dia
    fecha = models.DateField(default=timezone.localdate)
    texto = models.CharField(max_length=250)

    class Meta:
        db_table = "observaciones_vehiculo"
        verbose_name = "Observación de vehículo"
        verbose_name_plural = "Observaciones de vehículos"
        # De la mas nueva a la mas vieja; el id desempata las del mismo dia
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"Observación de {self.vehiculo} el {self.fecha:%d/%m/%Y}"


class Viaje(models.Model):
    """
    Que hizo el chofer con el sobrante de la caja al volver. Solo tiene sentido
    cuando final_caja > 0. "" es que todavia no se registro; "total" es que
    devolvio todo el sobrante y no queda nada pendiente; "parcial" es que
    devolvio una parte y se quedo con el resto, que pasa a figurar como un pago
    del empleado (pago_devolucion). Ver services.registrar_devolucion_caja.
    """
    DEVOLUCION_SIN_REGISTRAR = ""
    DEVOLUCION_TOTAL = "total"
    DEVOLUCION_PARCIAL = "parcial"
    DEVOLUCION_CHOICES = [
        (DEVOLUCION_SIN_REGISTRAR, "Sin registrar"),
        (DEVOLUCION_TOTAL, "Devolvió todo"),
        (DEVOLUCION_PARCIAL, "Devolvió una parte"),
    ]

    empleado = models.ForeignKey(Empleado, on_delete=models.PROTECT, db_column="id_empleado")
    vehiculo = models.ForeignKey(Vehiculo, on_delete=models.PROTECT, db_column="id_vehiculo")
    inicio_caja = models.PositiveIntegerField(default=0)
    fecha_inicio = models.DateField()
    fecha_vuelta = models.DateField(null=True, blank=True)
    activo = models.BooleanField(default=True)

    # Estado de la devolucion del sobrante (ver DEVOLUCION_CHOICES).
    devolucion_estado = models.CharField(
        max_length=10, choices=DEVOLUCION_CHOICES, default=DEVOLUCION_SIN_REGISTRAR, blank=True
    )
    # Cuanto devolvio el chofer del sobrante. En "total" es igual al sobrante.
    monto_devuelto = models.PositiveIntegerField(default=0)
    """
    Foto del sobrante (final_caja) al momento de registrar la devolucion. Se
    guarda para que el registro quede coherente aunque despues cambien las
    operaciones o los gastos y final_caja se mueva.
    """
    sobrante_devolucion = models.PositiveIntegerField(default=0)
    """
    El pago que genero una devolucion parcial (lo que el chofer se quedo). Es un
    PagosEmpleados con origen "devolucion". OneToOne para poder actualizarlo o
    borrarlo al editar la devolucion desde el viaje. SET_NULL: si el pago se
    borra desde el perfil del empleado, el viaje no se cae, solo pierde el vinculo.
    """
    pago_devolucion = models.OneToOneField(
        "PagosEmpleados", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="viaje_devolucion",
    )

    @property
    def total_gastos(self) -> int:
        from django.db.models import Sum

        # Suma todos los montos de la tabla Gasto asociados a este viaje
        resultado = self.detalle_gastos.aggregate(total=Sum('monto'))['total']
        if resultado is not None:
            return resultado
        else:
            return 0

    @cached_property
    def _operaciones_caja(self):
        """
        Ventas y compras activas del viaje en una sola consulta: en la caja del
        viaje las ventas ingresan dinero y las compras lo sacan. Sumo linea por
        linea (cantidad * precio) igual que la property monto_total de Operacion.
        """
        agg = self.operaciones.filter(activa=True).aggregate(
            ventas=Sum(F("detalleoperacion__cantidad") * F("detalleoperacion__precio_unitario"),
                       filter=Q(tipo_operacion="venta")),
            compras=Sum(F("detalleoperacion__cantidad") * F("detalleoperacion__precio_unitario"),
                        filter=Q(tipo_operacion="compra")),
        )
        return {
            "ventas": int(agg["ventas"] or 0),
            "compras": int(agg["compras"] or 0),
        }

    @property
    def total_ventas(self) -> int:
        return self._operaciones_caja["ventas"]

    @property
    def total_compras(self) -> int:
        return self._operaciones_caja["compras"]

    @property
    def total_ingresos(self) -> int:
        from django.db.models import Sum

        """
        Dinero que entra a la caja por fuera de las ventas (hoy, la transferencia
        que se le manda al chofer). Si el viaje no tiene ninguno, aggregate devuelve
        None y lo normalizo a 0.
        """
        resultado = self.ingresos_caja.aggregate(total=Sum('monto'))['total']
        return resultado if resultado is not None else 0

    @property
    def final_caja(self) -> int:
        """
        La caja arranca en inicio_caja, se le restan los gastos, se le suma lo
        vendido y lo transferido al chofer, y se le resta lo comprado. Puede
        quedar negativa.
        """
        return (int(self.inicio_caja) - self.total_gastos + self.total_ventas
                - self.total_compras + self.total_ingresos)

    @property
    def devolucion_registrada(self) -> bool:
        # La devolucion esta cargada cuando el estado no es el vacio.
        return self.devolucion_estado in (self.DEVOLUCION_TOTAL, self.DEVOLUCION_PARCIAL)

    @property
    def devolucion_retenido(self) -> int:
        """
        Lo que el chofer se quedo en una devolucion parcial: el sobrante del que
        se partio menos lo que devolvio. Es el monto que figura como pago del
        empleado. En "total" o sin registrar es cero.
        """
        if self.devolucion_estado != self.DEVOLUCION_PARCIAL:
            return 0
        return int(self.sobrante_devolucion) - int(self.monto_devuelto)

    @property
    def estado(self):
        from django.utils import timezone
        if self.fecha_vuelta:
            hoy = timezone.localdate()
            if hoy > self.fecha_vuelta:
                return "Finalizado"
        return "En curso"

    class Meta:
        db_table = "viajes"

    def __str__(self):
        return f"viaje {self.id}"


class DetalleViaje(models.Model):
    viaje = models.ForeignKey(Viaje, on_delete=models.CASCADE, related_name="destinos", db_column="id_viaje")
    destino = models.CharField(max_length=30)

    class Meta:
        db_table = "detalle_viajes"
        """
        Los destinos son el recorrido del viaje: el id los deja siempre en el
        orden en que se cargaron, en vez de depender de lo que devuelva la base.
        """
        ordering = ["id"]

    def __str__(self):
        return f"Destino {self.destino} (Viaje {self.viaje_id})"


class GastoBase(models.Model):
    TIPO_GASTOS = [
        ("Comida", "Comida"),
        ("Combustible", "Combustible"),
        ("Playa", "Playa"),
        ("Peaje", "Peaje"),
        ("Hotel", "Hotel"),
        ("Viaticos personales", "Viaticos personales"),
        ("Extras", "Extras")
    ]
    fecha = models.DateField(auto_now_add=True)
    gasto = models.CharField(choices=TIPO_GASTOS, max_length=25)
    monto = models.PositiveIntegerField(default=0)
    """
    Solo para los gastos de tipo Combustible: la carga de combustible que este
    gasto genero en una estacion de servicio. Queda en None para el resto de los
    gastos. Cada tabla de gasto (miel/cera, cereal, reparto) tiene su propia
    columna gracias a %(class)s. Al borrar la carga el gasto no se cae: solo
    pierde el vinculo (SET_NULL), pero en la practica se sincronizan juntos.
    """
    carga_combustible = models.OneToOneField(
        "CargaCombustible", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="%(class)s_gasto",
    )

    class Meta:
        abstract = True


class Gasto(GastoBase):
    # Para los viajes de miel/cera, la nombre gasto simplemente
    viaje = models.ForeignKey(Viaje, on_delete=models.CASCADE, related_name="detalle_gastos", db_column="id_viaje")

    class Meta:
        db_table = "gastos"

    def __str__(self):
        return f"Gasto {self.gasto} de {self.monto} pesos (Viaje: {self.viaje})"


class IngresoCaja(models.Model):
    """Dinero que entra a la caja del viaje por fuera de las ventas.

    Hoy tiene un unico concepto: la transferencia que se le manda al chofer para
    los gastos del viaje. Suma al Total restante igual que una venta, pero no es
    una operacion con cliente, asi que vive en su propia tabla. Solo miel/cera
    maneja caja (reparto y cereal calculan ganancia), por eso cuelga de Viaje.
    """
    viaje = models.ForeignKey(Viaje, on_delete=models.CASCADE, related_name="ingresos_caja", db_column="id_viaje")
    fecha = models.DateField(auto_now_add=True)
    monto = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "ingresos_caja"

    def __str__(self):
        return f"Ingreso a caja de {self.monto} pesos (Viaje: {self.viaje})"


class ViajeReparto(models.Model):
    fecha_viaje_reparto = models.DateField()
    empleado = models.ForeignKey(Empleado, on_delete=models.PROTECT, db_column="id_empleado")
    vehiculo = models.ForeignKey(Vehiculo, on_delete=models.PROTECT, db_column="id_vehiculo")
    """
    Localidad del reparto, elegida del catalogo. Es nullable solo para los repartos
    historicos que se cargaron con destinos escritos a mano y quedaron sin catalogo.
    Referencia por texto porque el catalogo se declara mas abajo en este mismo archivo.
    """
    destino = models.ForeignKey("DestinoViajeReparto", on_delete=models.PROTECT, null=True, blank=True,
                                db_column="id_destino", related_name="viajes")
    gasto_combustible_viaje_reparto = models.PositiveIntegerField(default=0)
    costo_empleado = models.PositiveIntegerField(default=0)
    """
    Decimal porque la tarifa del catalogo puede tener centavos y el viaje se
    queda con una copia de ese monto
    """
    valor_viaje = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    activo = models.BooleanField(default=True)
    pagado = models.BooleanField(default=False)
    """
    Momento en que se registro el cobro. Queda en None mientras el viaje esta
    impago y se limpia si el cobro se da de baja, asi nunca muestra una fecha
    que no corresponde al estado actual.
    """
    fecha_pago = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "viaje_reparto"

    @property
    def total_gastos(self) -> int:
        """
        Suma de los gastos extra cargados a este viaje de reparto (tabla hija).
        Si el viaje no tiene gastos, aggregate devuelve None y lo normalizo a 0.
        """
        resultado = self.detalle_gastos.aggregate(total=Sum('monto'))['total']
        return resultado if resultado is not None else 0

    # Ganancia: valor del viaje menos combustible, nomina del empleado y los gastos extra
    @property
    def ganancia(self):
        return self.valor_viaje - self.gasto_combustible_viaje_reparto - self.costo_empleado - self.total_gastos

    def __str__(self):
        return f"Viaje reparto nro: {self.id}"


class DetalleViajeReparto(models.Model):
    viaje_reparto = models.ForeignKey(ViajeReparto, on_delete=models.CASCADE,
                                      related_name="destinos", db_column="id_viajereparto")
    destinos_reparto = models.CharField(max_length=30)

    class Meta:
        db_table = "detalle_viaje_reparto"

    def __str__(self):
        return f"Destino {self.destinos_reparto} del {self.viaje_reparto}"


class GastoViajeReparto(GastoBase):
    viaje_reparto = models.ForeignKey(ViajeReparto, on_delete=models.CASCADE,
                                      related_name="detalle_gastos", db_column="id_viajereparto")

    class Meta:
        db_table = "gastos_viaje_reparto"

    def __str__(self):
        return f"Gasto {self.gasto} de {self.monto} pesos (Viaje reparto: {self.viaje_reparto})"


class DestinoViajeReparto(models.Model):
    """Catalogo de localidades a las que se reparte, con su tarifa ya pactada.

    Los repartos van a localidades cercanas que define Mercado Libre, no la
    empresa: por eso el destino se elige de esta lista en vez de escribirse a
    mano en cada viaje.
    """
    localidad_destino = models.CharField(max_length=60, unique=True)
    valor_viaje = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cant_viajes = models.PositiveIntegerField(default=0)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "destino_viaje_reparto"
        ordering = ["localidad_destino"]

    def __str__(self):
        return f"Localidad: {self.localidad_destino}, valor {self.valor_viaje}"


class ViajeCereal(models.Model):
    cereales = [
        ("Maiz", "Maiz"),
        ("Soja", "Soja"),
        ("Trigo", "Trigo"),
        ("Mani", "Mani")
    ]
    fecha_viaje_cereal = models.DateField()
    empleado = models.ForeignKey(Empleado, on_delete=models.PROTECT, db_column="id_empleado")
    vehiculo = models.ForeignKey(Vehiculo, on_delete=models.PROTECT, db_column="id_vehiculo")
    """
    Cliente al que se le presta el flete. Es nullable para no romper los viajes
    de cereal que ya existian antes de incorporar este campo (quedan "Sin cliente").
    """
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, null=True, blank=True,
                                db_column="id_cliente", related_name="viajes_cereales")
    tipo_cereal = models.CharField(max_length=50, choices=cereales)
    """
    El CTG es un codigo de hasta 15 digitos que puede tener ceros a la izquierda, por eso
    lo guardo como texto: un IntegerField perderia esos ceros (00123456 -> 123456)
    """
    codigo_trazabilidad_granos = models.CharField(max_length=15)
    """
    Numero de factura al que pertenece el viaje. Es texto y no entero por el mismo
    motivo que el CTG: puede tener ceros a la izquierda que un IntegerField perderia.
    Una misma factura puede repetirse en varios viajes (el operador la escribe a mano
    en cada uno). Es opcional: los viajes viejos sin factura quedan en None.
    """
    numero_factura = models.CharField(max_length=20, null=True, blank=True)
    """
    Toneladas transportadas. Uso Decimal (no Integer/Float) para admitir hasta dos
    decimales sin el ruido de precision del punto flotante, igual que en el resto de
    las cantidades comerciales del sistema (DetalleOperacion, ProductoPorKg).
    """
    toneladas = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    precio_tonelada = models.PositiveIntegerField(default=0)
    porcentaje_empleado = models.PositiveIntegerField(default=0)
    activo = models.BooleanField(default=True)
    pagado = models.BooleanField(default=False)
    """
    Momento en que se registro el cobro. Queda en None mientras el viaje esta
    impago y se limpia si el cobro se da de baja, asi nunca muestra una fecha
    que no corresponde al estado actual.
    """
    fecha_pago = models.DateTimeField(null=True, blank=True)

    """
    --- Dadora de carga ---
    La dadora es quien le consigue el flete al cliente. Es opcional: si el nombre
    queda vacio, el viaje no tuvo dadora (o no le cobro). Su comision se calcula
    sobre la facturacion (toneladas x precio), antes que los gastos: es lo primero
    que se descuenta apenas se factura el viaje.
    """
    COBROS_DADORA = [
        ("porcentaje", "Porcentaje"),
        ("tonelada", "Por tonelada"),
        ("efectivo", "Efectivo"),
    ]
    dadora_carga = models.CharField(max_length=60, blank=True, default="")
    """
    Como cobra la dadora, siempre sobre la facturacion: un porcentaje, un monto por
    cada tonelada, o un monto fijo en efectivo. Queda vacio cuando no hay dadora.
    """
    dadora_tipo_cobro = models.CharField(max_length=20, choices=COBROS_DADORA, blank=True, default="")
    """
    El valor cobrado, que se interpreta segun 'dadora_tipo_cobro': si es porcentaje
    va de 1 a 100; si es por tonelada son los pesos por cada tonelada; si es efectivo
    es el monto fijo. Queda en 0 cuando el viaje no tiene dadora.
    """
    dadora_valor = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "viaje_cereal"
        verbose_name = "Viaje cereal"
        verbose_name_plural = "Viajes cereales"

    @property
    def total_bruto(self):
        # Facturacion del flete: toneladas transportadas por el precio de cada una
        return self.toneladas * self.precio_tonelada

    @property
    def total_gastos(self) -> int:
        """
        Suma de todos los gastos cargados a este viaje de cereal. Si el viaje no
        tiene gastos, aggregate devuelve None y lo normalizo a 0.
        """
        resultado = self.detalle_gastos.aggregate(total=Sum('monto'))['total']
        return resultado if resultado is not None else 0

    @property
    def tiene_dadora(self):
        # El nombre vacio es la marca de "este viaje no tuvo dadora de carga".
        return bool(self.dadora_carga)

    @property
    def costo_dadora(self):
        """
        Comision de la dadora, lo primero que se descuenta de la facturacion (antes
        que los gastos). Segun como cobre:
         - porcentaje: un porcentaje de la facturacion (toneladas x precio).
         - tonelada: una cantidad de toneladas valuadas al precio del viaje. Si la
           dadora se lleva "1 tonelada", cobra el precio de una tonelada de este
           viaje (dadora_valor toneladas x precio_tonelada).
         - efectivo: un monto fijo.
        Sin dadora no hay costo.
        """
        if not self.tiene_dadora:
            return 0
        if self.dadora_tipo_cobro == "porcentaje":
            return self.total_bruto * self.dadora_valor / 100
        if self.dadora_tipo_cobro == "tonelada":
            return self.dadora_valor * self.precio_tonelada
        if self.dadora_tipo_cobro == "efectivo":
            return self.dadora_valor
        return 0

    @property
    def subtotal(self):
        """
        Base sobre la que se reparte el empleado: la facturacion menos la comision
        de la dadora (que sale primero) y menos los gastos del viaje.
        """
        return self.total_bruto - self.costo_dadora - self.total_gastos

    @property
    def pago_empleado(self):
        """
        Lo que se lleva el empleado segun su porcentaje sobre el subtotal (ya
        descontadas la dadora y los gastos). Si el subtotal es negativo tomo la base
        en 0 para no calcular un pago negativo.
        """
        base = self.subtotal if self.subtotal > 0 else 0
        return base * self.porcentaje_empleado / 100

    @property
    def ganancia_neta(self):
        """
        Lo que le queda a la empresa: el subtotal (ya descontadas dadora y gastos)
        menos la parte del empleado. Puede ser negativo si los costos superan la
        facturacion.
        """
        return self.subtotal - self.pago_empleado

    def __str__(self):
        return f"Viaje de cereal nro: {self.id}"


class DetalleViajeCereal(models.Model):
    viaje_cereal = models.ForeignKey(ViajeCereal, on_delete=models.CASCADE,
                                     related_name="destinos", db_column="id_viajecereal")
    destino = models.CharField(max_length=30)

    class Meta:
        db_table = "detalle_viaje_cereal"
        # Mismo criterio que los destinos de miel/cera: orden de carga, estable.
        ordering = ["id"]

    def __str__(self):
        return f"Destino {self.destino} del {self.viaje_cereal}"


class GastoViajeCereal(GastoBase):
    viaje_cereal = models.ForeignKey(ViajeCereal, on_delete=models.CASCADE,
                                     related_name="detalle_gastos", db_column="id_viajecereal")

    class Meta:
        db_table = "gastos_viaje_cereal"

    def __str__(self):
        return f"Gasto {self.gasto} de {self.monto} pesos (Viaje cereal: {self.viaje_cereal})"


def periodo_actual():
    """Primer dia del mes en curso.

    Txdo el modulo de alquileres identifica un mes por su dia 1: asi el periodo
    entra en un DateField comun, se ordena y se compara sin trucos, y "julio de
    2026" es siempre el mismo valor lo escriba quien lo escriba.
    """
    hoy = timezone.localdate()
    return date(hoy.year, hoy.month, 1)


def mes_siguiente(periodo):
    """Primero del mes que sigue al periodo. Sirve para comparar con un "menor que"
    y quedarse con txdo el mes, sin tener que averiguar si tiene 28, 30 o 31 dias.
    """
    return date(periodo.year + periodo.month // 12, periodo.month % 12 + 1, 1)


def contratos_del_periodo(periodo):
    """Filtro de los contratos que cubren un mes, del mas nuevo al mas viejo.

    Un contrato cubre el mes si ya habia empezado (arranco antes del mes siguiente)
    y todavia no habia terminado. Que el fin se compare contra el dia 1 y no contra
    el ultimo es a proposito: el contrato que vence el 15 de agosto cubre agosto
    entero, porque el alquiler de ese mes se devengo igual.

    El fin vacio es un contrato sin vencimiento cargado y no caduca nunca.
    """
    return (Contrato.objects
            .filter(Q(fin__isnull=True) | Q(fin__gte=periodo), inicio__lt=mes_siguiente(periodo))
            .order_by("-inicio", "-id"))


class CasaQuerySet(models.QuerySet):
    def con_estado_del_mes(self, periodo=None):
        """Anota txdo lo que del estado de una casa depende del mes que se mira.

        Son cuatro datos: cuanto se cobro y, del contrato que cubria ese mes, si
        existio y con que numeros. Sin esto, pintar el estado de cada fila dispara
        varias queries por casa (el mismo N+1 que evita Operacion.con_totales).

        Un mes tiene a lo sumo un pago, asi que la suma devuelve ese unico monto
        y el cero significa que todavia no se cobro. Sumo en vez de preguntar si
        existe porque el listado tambien muestra cuanto entro, no solo si entro.

        Los numeros del alquiler se leen del contrato de ESE mes y no del ultimo
        cargado: asi un mes viejo se calcula con el precio que regia entonces, que
        es lo que antes no tenia arreglo mientras el precio vivia en la casa.
        """
        periodo = periodo or periodo_actual()
        pagos_periodo = (
            PagoAlquiler.objects.filter(casa=OuterRef("pk"), periodo=periodo)
            .values("casa")
            .annotate(total=Sum("monto"))
            .values("total")
        )
        vigente = contratos_del_periodo(periodo).filter(casa=OuterRef("pk"))
        """
        El ultimo contrato que ya habia terminado antes de este mes. Solo se usa
        para poder decir "contrato vencido" en vez de dejar la casa muda.
        """
        anterior = (Contrato.objects.filter(casa=OuterRef("pk"), fin__lt=periodo)
                    .order_by("-fin", "-id"))
        """
        Contrato corriendo HOY, que no es lo mismo que el del mes que se mira:
        el boton de contrato carga siempre el que sigue al de hoy, asi que se
        bloquea o no segun la fecha real y no segun el mes que este en pantalla.
        """
        hoy = timezone.localdate()
        corriendo = Contrato.objects.filter(
            Q(fin__isnull=True) | Q(fin__gte=hoy), casa=OuterRef("pk"), inicio__lte=hoy
        )

        return self.annotate(
            _pagado_periodo_anotado=Coalesce(
                Subquery(pagos_periodo, output_field=DecimalField()),
                Value(0),
                output_field=DecimalField(),
            ),
            _contrato_periodo_anotado=Subquery(vigente.values("id")[:1]),
            _monto_periodo_anotado=Subquery(vigente.values("monto_mensual")[:1],
                                            output_field=IntegerField()),
            _comision_periodo_anotado=Subquery(vigente.values("comision_inmobiliaria")[:1],
                                               output_field=IntegerField()),
            _fin_anterior_anotado=Subquery(anterior.values("fin")[:1], output_field=DateField()),
            _contrato_hoy_anotado=Exists(corriendo),
        )


class Casa(models.Model):
    """Propiedad que la empresa da en alquiler.

    Guarda solo lo que es de la casa y no cambia con el inquilino: donde esta y
    como se llama. Txdo lo del alquiler (plazo, monto, comision, inquilino) vive
    en Contrato, porque una casa tiene varios a lo largo del tiempo y el de hoy
    no puede pisar al del año pasado.

    Ningun dato es obligatorio: una casa se puede dar de alta con el nombre solo
    y completarse despues.
    """
    objects = CasaQuerySet.as_manager()

    nombre = models.CharField(max_length=60, null=True, blank=True)
    localidad = models.CharField(max_length=60, null=True, blank=True)
    direccion = models.CharField(max_length=120, null=True, blank=True)
    activa = models.BooleanField(default=True)

    class Meta:
        db_table = "casas"
        verbose_name_plural = "Casas"
        ordering = ["nombre", "id"]

    @property
    def contrato_del_periodo(self):
        """Contrato que cubre el mes que se esta mirando, o None.

        Si la casa vino de con_estado_del_mes() no vuelve a la base: las columnas
        que hacen falta ya llegaron anotadas. Suelta si consulta, y cachea, porque
        de este contrato cuelgan tres propiedades y seria una query cada una.
        """
        if not hasattr(self, "_contrato_cacheado"):
            self._contrato_cacheado = (
                contratos_del_periodo(periodo_actual()).filter(casa=self).first()
            )
        return self._contrato_cacheado

    @property
    def alquilada(self):
        """Si en el mes que se mira habia contrato. Reemplaza al viejo booleano.

        No hay nada que marcar a mano ni que apagar cuando un contrato vence: el
        dia que deja de haber contrato que cubra el mes, la casa figura sin
        alquilar sola. Y un mes pasado dice lo que pasaba entonces, no hoy.
        """
        if hasattr(self, "_contrato_periodo_anotado"):
            return self._contrato_periodo_anotado is not None
        return self.contrato_del_periodo is not None

    @property
    def precio(self):
        """
        Alquiler mensual del contrato de ese mes. Sin contrato no hay precio: la
        casa no esta alquilada y no hay nada que cobrar.
        """
        if hasattr(self, "_monto_periodo_anotado"):
            return self._monto_periodo_anotado
        contrato = self.contrato_del_periodo
        return contrato.monto_mensual if contrato else None

    @property
    def comision_inmobiliaria(self):
        """
        Porcentaje del alquiler (0 a 100) que se lleva la inmobiliaria. Se guarda
        como porcentaje y no como monto para que acompañe solo a cada aumento.
        """
        if hasattr(self, "_comision_periodo_anotado"):
            return self._comision_periodo_anotado
        contrato = self.contrato_del_periodo
        return contrato.comision_inmobiliaria if contrato else None

    @property
    def tiene_contrato_vigente(self):
        """Si hoy hay un contrato corriendo. Distinto de 'alquilada', que habla del
        mes que se esta mirando en pantalla.

        De esto depende que el boton de contrato este bloqueado: mientras haya uno
        vigente no hay ninguno nuevo que cargar, y el que se cargara se solaparia.
        """
        if hasattr(self, "_contrato_hoy_anotado"):
            return bool(self._contrato_hoy_anotado)
        hoy = timezone.localdate()
        return self.contratos.filter(
            Q(fin__isnull=True) | Q(fin__gte=hoy), inicio__lte=hoy
        ).exists()

    @property
    def fin_contrato_anterior(self):
        """
        Cuando termino el ultimo contrato, si es que ya termino antes de este mes.
        Es lo que separa "se le vencio el contrato" de "nunca estuvo alquilada".
        """
        if hasattr(self, "_fin_anterior_anotado"):
            return self._fin_anterior_anotado
        ultimo = self.contratos.filter(fin__lt=periodo_actual()).order_by("-fin", "-id").first()
        return ultimo.fin if ultimo else None

    @property
    def comision_monto(self):
        """
        Cuanto se lleva la inmobiliaria por mes. Sin precio cargado no hay nada
        que calcular; sin comision cargada, la casa se administra sola y es cero.
        """
        if self.precio is None:
            return None
        porcentaje = self.comision_inmobiliaria or 0
        return (self.precio * porcentaje / Decimal("100")).quantize(Decimal("0.01"))

    @property
    def neto_mensual(self):
        # Lo que le queda a la empresa una vez descontada la inmobiliaria
        if self.precio is None:
            return None
        return self.precio - self.comision_monto

    @property
    def total_pagado_periodo(self):
        """
        Cobrado del periodo. Si el queryset vino de con_estado_del_mes() uso ese
        valor ya calculado, que ademas es el que fija que mes se esta mirando;
        suelto, sin anotacion, cae en el mes en curso.
        """
        if hasattr(self, "_pagado_periodo_anotado"):
            return self._pagado_periodo_anotado or Decimal("0")
        return self.pagos.filter(periodo=periodo_actual()).aggregate(total=Sum("monto"))["total"] or Decimal("0")

    @property
    def cobrada_en_el_periodo(self):
        """
        El alquiler se cobra entero o no se cobra, asi que alcanza con saber si
        hay un pago cargado en el mes: no hay monto que comparar contra el precio.
        """
        return self.total_pagado_periodo > 0

    @property
    def estado_mes(self):
        """Estado del alquiler en el periodo que se este mirando.

        Tres estados y ninguno se guarda en un campo: salen de si hay un pago con
        periodo igual al mes en cuestion. Por eso, al cambiar el mes, la casa
        vuelve sola a "Pendiente de cobro" sin que nadie tenga que resetear nada
        ni corra ningun proceso el dia 1.

        No existe el estado parcial: un alquiler se paga completo. Si el mes tiene
        pago, esta cobrado.

        El pago se pregunta primero y le gana al contrato. Un pago cargado es un
        hecho de ese mes; el contrato dice lo que se habia pactado, y si alguien
        cobro igual, se cobro. Al reves, una casa que se desocupo hacia figurar
        sin alquilar un mes que en realidad habia cobrado.

        Un contrato vencido cae en "Sin alquilar" y no en un estado propio: para el
        mes que se esta mirando significan lo mismo, que no hay alquiler que
        reclamar. La tabla si lo aclara al lado del nombre, porque el motivo no es
        el mismo y de eso depende que el usuario renueve.
        """
        if self.cobrada_en_el_periodo:
            return "Cobrado"
        if not self.alquilada:
            return "Sin alquilar"
        return "Pendiente de cobro"

    def __str__(self):
        return self.nombre or f"Casa {self.id}"


class Contrato(models.Model):
    """Alquiler pactado de una casa por un plazo: quien, cuanto y hasta cuando.

    Una casa tiene varios a lo largo del tiempo y nunca dos a la vez. Renovar es
    guardar uno nuevo, no editar el viejo: por eso el del año pasado sigue entero
    y los meses de entonces se calculan con el monto de entonces.

    Las dos fechas son obligatorias: de ellas cuelga el estado de la casa mes a
    mes, y sin fin el contrato no vence nunca, asi que la casa jamas pasaria sola
    a figurar sin alquilar. Lo piden el formulario, el servicio y el admin.

    La columna todavia acepta null por una sola razon: los contratos que trajo la
    migracion desde la tabla de casas quedaron sin fin, porque la casa no guardaba
    esa fecha. Es un estado heredado y no una opcion; cuando esos contratos tengan
    su vencimiento, el null se saca de la base con una migracion.
    """
    casa = models.ForeignKey(Casa, on_delete=models.CASCADE, related_name="contratos",
                             db_column="id_casa")
    inicio = models.DateField()
    fin = models.DateField(null=True)
    monto_mensual = models.PositiveIntegerField()
    comision_inmobiliaria = models.PositiveIntegerField(null=True, blank=True)
    nombre_inquilino = models.CharField(max_length=60, null=True, blank=True)

    class Meta:
        db_table = "contratos"
        verbose_name_plural = "Contratos"
        # Del mas nuevo al mas viejo; el id desempata los que arrancan el mismo dia
        ordering = ["-inicio", "-id"]

    @property
    def vencido(self):
        return self.fin is not None and self.fin < timezone.localdate()

    @property
    def comision_monto(self):
        """Cuanto se lleva la inmobiliaria por mes, en pesos.

        La misma cuenta que Casa.comision_monto, pero sobre el contrato en si.
        La de la casa sale de las anotaciones del mes que se este mirando y solo
        sirve para el listado; esta vale para cualquier contrato, incluso los del
        historial, que es lo que necesita el perfil.

        Sin comision cargada la casa se administra sola y no se lleva nada.
        """
        porcentaje = self.comision_inmobiliaria or 0
        return (self.monto_mensual * porcentaje / Decimal("100")).quantize(Decimal("0.01"))

    @property
    def neto_mensual(self):
        # Lo que le queda a la empresa una vez descontada la inmobiliaria
        return self.monto_mensual - self.comision_monto

    @property
    def meses(self):
        """Duracion en meses, redondeada hacia arriba, o None si no tiene fin.

        Cuenta meses arrancados y no completos: del 15/01 al 14/01 son doce meses
        de alquiler, aunque el ultimo no llegue a cerrar el dia.
        """
        if self.fin is None:
            return None
        cuenta = (self.fin.year - self.inicio.year) * 12 + (self.fin.month - self.inicio.month)
        return cuenta + 1 if self.fin.day >= self.inicio.day else cuenta

    def __str__(self):
        hasta = self.fin.strftime("%d/%m/%Y") if self.fin else "sin vencimiento"
        return f"Contrato de {self.casa} desde {self.inicio:%d/%m/%Y} hasta {hasta}"


class GastoCasa(models.Model):
    """Plata que la casa se come: impuestos, tasas, arreglos, servicios.

    Cuelga de la casa y no del contrato, a proposito: el impuesto inmobiliario y
    el arreglo del techo se pagan este alquilada o vacia, y siguen siendo de la
    casa cuando el inquilino cambia.

    No hereda de GastoBase, que es el gasto de un viaje, porque no le sirve
    ninguno de los tres campos: la fecha es auto_now_add y aca hay que poder
    cargar una boleta de la semana pasada, el monto es entero y estos llevan
    centavos, y las categorias son de ruta (combustible, peaje, hotel).
    """
    CATEGORIAS = [
        ("Impuestos", "Impuestos"),
        ("Tasas municipales", "Tasas municipales"),
        ("Mantenimiento", "Mantenimiento"),
        ("Servicios", "Servicios"),
        ("Seguro", "Seguro"),
        ("Otros", "Otros"),
    ]

    casa = models.ForeignKey(Casa, on_delete=models.CASCADE, related_name="gastos",
                             db_column="id_casa")
    """
    default y no auto_now_add: el gasto se carga cuando se puede, no el dia que
    se pago, y la fecha de la boleta es la que vale
    """
    fecha = models.DateField(default=timezone.localdate)
    categoria = models.CharField(max_length=30, choices=CATEGORIAS)
    # Opcional: la categoria ya ubica el gasto, el detalle solo lo aclara
    detalle = models.CharField(max_length=120, null=True, blank=True)
    monto = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        db_table = "gastos_casas"
        verbose_name = "Gasto de casa"
        verbose_name_plural = "Gastos de casas"
        # Del mas nuevo al mas viejo; el id desempata los del mismo dia
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"{self.categoria} de {self.monto} el {self.fecha:%d/%m/%Y} ({self.casa})"


class PagoAlquiler(models.Model):
    """Cobro del alquiler de una casa. Cubre un mes entero.

    Guardo por separado cuando entro la plata (fecha) y que mes cubre (periodo)
    porque no siempre coinciden: el alquiler de julio se puede cobrar el 3 de
    agosto. Si el estado del mes se dedujera de la fecha del pago, julio quedaria
    pendiente para siempre y agosto figuraria cobrado sin estarlo.

    Un mes se paga una sola vez, y de eso se encarga la restriccion unica de
    abajo: si el alquiler se cobra completo, dos pagos del mismo mes para la
    misma casa no son un cobro en cuotas sino un error de carga.
    """
    casa = models.ForeignKey(Casa, on_delete=models.CASCADE, related_name="pagos", db_column="id_casa")
    # default (y no auto_now_add) para poder cargar un cobro que se hizo hace unos dias
    fecha = models.DateField(default=timezone.now)
    # Mes que cubre el pago, siempre normalizado al dia 1 (ver periodo_actual)
    periodo = models.DateField(default=periodo_actual)
    monto = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        db_table = "pagos_alquileres"
        verbose_name = "Pago de alquiler"
        verbose_name_plural = "Pagos de alquileres"
        # Del mes mas nuevo al mas viejo; el id desempata los que caen el mismo dia
        ordering = ["-periodo", "-fecha", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["casa", "periodo"], name="unique_pago_alquiler_casa_periodo"
            ),
        ]

    @property
    def periodo_label(self):
        """
        "07/2026". El nombre del mes lo arma la plantilla con el filtro date,
        aca dejo algo corto y sin depender del locale para listados y logs.
        """
        return self.periodo.strftime("%m/%Y")

    def __str__(self):
        return f"Pago de {self.monto} del periodo {self.periodo_label} ({self.casa})"


class EstacionDeServicio(models.Model):
    nombre = models.CharField(max_length=30, unique=True)
    activa = models.BooleanField(default=True)

    class Meta:
        db_table = "estaciones_de_servicio"
        verbose_name = "Estacion de servicio"
        verbose_name_plural = "Estaciones de servicio"
        # Alfabetico como el resto de los catalogos: el id solo desempata
        ordering = ["nombre", "id"]

    @property
    def tiene_deuda(self):
        """True si queda al menos una carga activa sin pagar.

        El saldo no se guarda: se deriva de las cargas para no descuadrarse. En el
        listado se anota con Exists (_tiene_deuda_anotado) y asi se evita una query
        por fila; suelta, cae al exists() directo.
        """
        if hasattr(self, "_tiene_deuda_anotado"):
            return self._tiene_deuda_anotado
        return self.cargas.filter(activa=True, pagada=False).exists()

    @property
    def total_deuda(self):
        """Suma de los montos de las cargas activas impagas. 0 si no debe nada.

        Mismo criterio que tiene_deuda: el saldo se deriva de las cargas. En el
        listado se anota con _total_deuda_anotado para evitar una query por fila;
        suelta, cae al aggregate directo.
        """
        if hasattr(self, "_total_deuda_anotado"):
            return self._total_deuda_anotado or 0
        agregado = self.cargas.filter(activa=True, pagada=False).aggregate(total=Sum("monto"))
        return agregado["total"] or 0

    @property
    def estado_deuda(self):
        # Etiqueta para la columna de estado: no muestra numeros, solo si debe o no
        return "Debe" if self.tiene_deuda else "Todo pago"

    def __str__(self):
        return self.nombre


class CargaCombustible(models.Model):
    estacion = models.ForeignKey(EstacionDeServicio, on_delete=models.PROTECT, related_name="cargas")
    empleado = models.ForeignKey(Empleado, on_delete=models.PROTECT, related_name="cargas_combustible")
    vehiculo = models.ForeignKey(Vehiculo, on_delete=models.PROTECT, related_name="cargas_combustible")
    fecha = models.DateField()
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    # Litros cargados: dato opcional (a veces solo se conoce el monto)
    litros = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    # Estado binario: una carga esta paga o no lo esta (sin pagos parciales)
    pagada = models.BooleanField(default=False)
    activa = models.BooleanField(default=True)

    """
    Origen de la carga. Si nacio dentro de un viaje, apunta a ese viaje (uno solo
    de los tres, segun el tipo); el resto quedan en None. Una carga cargada a mano
    desde la estacion tiene los tres en None. Sirve para diferenciarla en el
    listado y para llevar al viaje donde se hizo el gasto.
    """
    viaje = models.ForeignKey("Viaje", on_delete=models.CASCADE, null=True, blank=True,
                              related_name="cargas_combustible")
    viaje_reparto = models.ForeignKey("ViajeReparto", on_delete=models.CASCADE, null=True, blank=True,
                                      related_name="cargas_combustible")
    viaje_cereal = models.ForeignKey("ViajeCereal", on_delete=models.CASCADE, null=True, blank=True,
                                     related_name="cargas_combustible")

    class Meta:
        db_table = "cargas_combustible"
        verbose_name = "Carga de combustible"
        verbose_name_plural = "Cargas de combustible"
        # De la mas nueva a la mas vieja, como el resto de los historiales
        ordering = ["-fecha", "-id"]

    @property
    def estado_pago(self):
        return "Pagada" if self.pagada else "Impaga"

    @property
    def viaje_asociado(self):
        # El unico viaje que tiene seteado, o None si es una carga manual.
        return self.viaje or self.viaje_reparto or self.viaje_cereal

    @property
    def de_viaje(self):
        """
        True si la carga nacio dentro de un viaje (no se cargo a mano). Uso los
        ids para no traer los objetos viaje (evita una query por fila en el listado).
        """
        return bool(self.viaje_id or self.viaje_reparto_id or self.viaje_cereal_id)

    @property
    def viaje_url(self):
        """
        URL del detalle del viaje que origino la carga, para llevar al usuario al
        viaje donde se hizo el gasto. Vacia si la carga se cargo a mano. Lleva el id
        de la estacion como volver_estacion, asi el boton "volver" del viaje puede
        devolver a esta ficha en vez de al listado de viajes.
        """
        from django.urls import reverse
        if self.viaje_id:
            destino = reverse("informacion_viaje", kwargs={"id_viaje": self.viaje_id})
        elif self.viaje_reparto_id:
            destino = reverse("informacion_viaje_reparto", kwargs={"id_viaje_reparto": self.viaje_reparto_id})
        elif self.viaje_cereal_id:
            destino = reverse("informacion_viaje_cereal", kwargs={"id_viaje_cereal": self.viaje_cereal_id})
        else:
            return ""
        return f"{destino}?volver_estacion={self.estacion_id}"

    @property
    def viaje_etiqueta(self):
        # Texto corto para el chip que diferencia la carga en el listado.
        if self.viaje_id:
            return f"Viaje miel/cera #{self.viaje_id}"
        if self.viaje_reparto_id:
            return f"Viaje reparto #{self.viaje_reparto_id}"
        if self.viaje_cereal_id:
            return f"Viaje cereal #{self.viaje_cereal_id}"
        return ""

    def __str__(self):
        return f"Carga de {self.monto} en {self.estacion} ({self.fecha})"


def _expresion_iva():
    """Suma del IVA de un grupo de operaciones: base imponible por su alicuota.

    Cada operacion aporta monto_neto * alicuota / 100. Lo dejo en una funcion y no
    en una constante porque una misma expresion no se puede reusar en dos subqueries
    distintas sin arrastrar estado; asi cada subquery arma la suya limpia.
    """
    return Sum(F("monto_neto") * F("alicuota") / Value(100), output_field=DecimalField())


class EmpresaQuerySet(models.QuerySet):
    def con_totales_iva(self):
        """Anota el IVA debito y el credito de cada empresa en una sola query.

        El debito sale de las operaciones de venta y el credito de las de compra;
        cada una aporta su base imponible por la alicuota (ver _expresion_iva). Uso
        dos subqueries separadas y no un unico JOIN con filtros para no sufrir el
        fan-out que multiplicaria los montos al cruzar ventas con compras, igual
        que Operacion.con_totales().
        """
        debito = (
            OperacionIva.objects.filter(empresa=OuterRef("pk"), tipo="venta")
            .values("empresa")
            .annotate(total=_expresion_iva())
            .values("total")
        )
        credito = (
            OperacionIva.objects.filter(empresa=OuterRef("pk"), tipo="compra")
            .values("empresa")
            .annotate(total=_expresion_iva())
            .values("total")
        )
        return self.annotate(
            _iva_debito_anotado=Coalesce(
                Subquery(debito, output_field=DecimalField()),
                Value(0),
                output_field=DecimalField(),
            ),
            _iva_credito_anotado=Coalesce(
                Subquery(credito, output_field=DecimalField()),
                Value(0),
                output_field=DecimalField(),
            ),
        )

    def con_totales_cheques(self, anio=None, mes=None):
        """Anota el total de cheques a pagar de cada empresa.

        Los cheques son siempre a pagar (plata que sale), asi que el total a pagar
        es todo lo que hay para saldar. Una subquery con Sum sobre los cheques de
        las cuentas activas, igual que con_totales_iva() pero de un solo tipo.

        Con 'anio' (y opcionalmente 'mes') acota a los cheques cuya fecha de cobro
        cae en ese periodo: es la fecha con la que el listado agrupa mes a mes. Sin
        periodo suma todos los pendientes, como en la ficha de la empresa.
        """
        filtros = {
            "cuenta_corriente__empresa": OuterRef("pk"),
            "cuenta_corriente__activa": True,
            "cobrado": False,
        }
        if anio:
            filtros["fecha_cobro__year"] = anio
        if mes:
            filtros["fecha_cobro__month"] = mes
        a_pagar = (
            Cheque.objects.filter(**filtros)
            .values("cuenta_corriente__empresa")
            .annotate(total=Sum("importe"))
            .values("total")
        )
        return self.annotate(
            _cheques_a_pagar_anotado=Coalesce(
                Subquery(a_pagar, output_field=DecimalField()),
                Value(0),
                output_field=DecimalField(),
            ),
        )


class Empresa(models.Model):
    """Empresa o sociedad de la que se controla el IVA.

    El sistema lo usan tres entidades para ver, cada una, cuanto IVA debito
    juntaron con sus ventas y cuanto credito con sus compras. La empresa no
    guarda esos totales: se derivan de sus operaciones para no descuadrarse
    (ver iva_debito / iva_credito / saldo_iva), del mismo modo que la estacion
    deriva su deuda de las cargas.

    Lo unico propio de la empresa es el nombre. La baja es logica (activa=False)
    para no perder las operaciones cargadas.
    """
    objects = EmpresaQuerySet.as_manager()

    nombre = models.CharField(max_length=60, unique=True)
    activa = models.BooleanField(default=True)

    class Meta:
        db_table = "empresas"
        verbose_name_plural = "Empresas"
        ordering = ["nombre", "id"]

    @property
    def iva_debito(self):
        """IVA debito fiscal: el IVA de todas las operaciones de venta.

        Si el queryset vino de con_totales_iva() reuso el valor ya anotado para no
        disparar una query por empresa en el listado; suelta, cae al aggregate.
        """
        if hasattr(self, "_iva_debito_anotado"):
            return self._iva_debito_anotado or Decimal("0")
        total = self.operaciones.filter(tipo="venta").aggregate(t=_expresion_iva())["t"]
        return total or Decimal("0")

    @property
    def iva_credito(self):
        """IVA credito fiscal: el IVA de todas las operaciones de compra."""
        if hasattr(self, "_iva_credito_anotado"):
            return self._iva_credito_anotado or Decimal("0")
        total = self.operaciones.filter(tipo="compra").aggregate(t=_expresion_iva())["t"]
        return total or Decimal("0")

    @property
    def saldo_iva(self):
        """Saldo tecnico del periodo: debito menos credito.

        Positivo es saldo a pagar (se le debe al fisco); negativo es saldo a favor
        (queda para descontar el mes siguiente); cero es que esta al dia.
        """
        return (self.iva_debito - self.iva_credito).quantize(Decimal("0.01"))

    @property
    def saldo_iva_abs(self):
        """
        El signo del saldo lo comunica la etiqueta (a pagar / a favor), asi que
        la tarjeta muestra el monto en positivo y no un "-$" que confunde.
        """
        return abs(self.saldo_iva)

    @property
    def estado_saldo(self):
        # Etiqueta corta del saldo, para el chip de la tarjeta y la ficha
        saldo = self.saldo_iva
        if saldo > 0:
            return "a_pagar"
        if saldo < 0:
            return "a_favor"
        return "al_dia"

    """
    --- CHEQUES ---------------------------------------------------------
    La empresa maneja sus cheques a pagar (nunca recibe cheques), agrupados por
    sus cuentas corrientes. El total a pagar es independiente del saldo de IVA.
    """

    @property
    def cheques_a_pagar(self):
        """Total a pagar en cheques de todas las cuentas corrientes de la empresa."""
        if hasattr(self, "_cheques_a_pagar_anotado"):
            return self._cheques_a_pagar_anotado or Decimal("0")
        total = (Cheque.objects.filter(cuenta_corriente__empresa=self,
                                       cuenta_corriente__activa=True,
                                       cobrado=False).aggregate(t=Sum("importe"))["t"])
        return total or Decimal("0")

    def __str__(self):
        return self.nombre


class OperacionIva(models.Model):
    """Operacion de venta o compra de una empresa, con su IVA.

    Es la unidad de la que se derivan los totales de la empresa: una venta suma
    IVA debito y una compra suma IVA credito. Guardo el monto neto (base
    imponible, sin IVA) y la alicuota, y el importe de IVA se calcula (ver iva);
    no lo persisto para que no pueda quedar desalineado con la base.
    """
    TIPOS = [
        ("venta", "Venta"),
        ("compra", "Compra"),
    ]
    """
    Alicuotas de IVA vigentes en Argentina: 21% general, 10,5% reducida y 27%
    aumentada. Se guardan como porcentaje (21.00) y con eso se calcula el IVA.
    """
    ALICUOTAS = [
        (Decimal("21.00"), "21%"),
        (Decimal("10.50"), "10,5%"),
        (Decimal("27.00"), "27%"),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="operaciones",
                                db_column="id_empresa")
    tipo = models.CharField(max_length=10, choices=TIPOS)
    """
    default y no auto_now_add: la operacion se carga cuando se puede y la fecha
    que vale es la del comprobante, no la de la carga
    """
    fecha = models.DateField(default=timezone.localdate)
    # Base imponible en pesos, sin IVA
    monto_neto = models.DecimalField(max_digits=15, decimal_places=2)
    # Alicuota aplicada, en porcentaje
    alicuota = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("21.00"))
    # Opcional: nro de factura o concepto para identificar la operacion
    detalle = models.CharField(max_length=120, null=True, blank=True)

    class Meta:
        db_table = "operaciones_iva"
        verbose_name = "Operacion de IVA"
        verbose_name_plural = "Operaciones de IVA"
        # De la mas nueva a la mas vieja; el id desempata las del mismo dia
        ordering = ["-fecha", "-id"]

    @property
    def iva(self):
        # Importe de IVA: base imponible por la alicuota
        return (self.monto_neto * self.alicuota / Decimal("100")).quantize(Decimal("0.01"))

    @property
    def total(self):
        # Monto final con IVA incluido
        return self.monto_neto + self.iva

    @property
    def es_venta(self):
        return self.tipo == "venta"

    def __str__(self):
        return f"{self.get_tipo_display()} de {self.monto_neto} ({self.empresa})"


class Banco(models.Model):
    """Banco de una cuenta corriente. Catalogo compartido por todas las empresas.

    Lo unico propio es el nombre. La baja es logica (activo=False) para no perder
    las cuentas corrientes y los cheques que lo referencian, igual que la estacion
    de servicio en combustible.
    """
    nombre = models.CharField(max_length=60, unique=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "bancos"
        verbose_name_plural = "Bancos"
        ordering = ["nombre", "id"]

    def __str__(self):
        return self.nombre


class CuentaCorrienteQuerySet(models.QuerySet):
    def con_totales_cheques(self):
        """Anota el total a pagar de cada cuenta corriente en una sola query.

        Una subquery con Sum sobre los cheques de la cuenta, igual que
        EmpresaQuerySet.con_totales_cheques() pero al nivel de la cuenta.
        """
        a_pagar = (
            Cheque.objects.filter(cuenta_corriente=OuterRef("pk"), cobrado=False)
            .values("cuenta_corriente")
            .annotate(total=Sum("importe"))
            .values("total")
        )
        return self.annotate(
            _a_pagar_anotado=Coalesce(
                Subquery(a_pagar, output_field=DecimalField()),
                Value(0),
                output_field=DecimalField(),
            ),
        )


class CuentaCorriente(models.Model):
    """Cuenta corriente de una empresa en un banco.

    Es la cuenta bancaria desde/hacia la que se emiten los cheques: pertenece a una
    empresa y a un banco, y su numero la identifica. El total a pagar se deriva
    de los cheques que cuelgan de ella (ver cheques_a_pagar); la baja es logica para
    no perder ese historial.
    """
    objects = CuentaCorrienteQuerySet.as_manager()

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="cuentas_corrientes",
                                db_column="id_empresa")
    """
    PROTECT y no CASCADE: un banco no se borra (baja logica); PROTECT evita que un
    borrado real accidental en el admin se lleve puesta las cuentas y sus cheques.
    """
    banco = models.ForeignKey(Banco, on_delete=models.PROTECT, related_name="cuentas_corrientes",
                              db_column="id_banco")
    numero = models.CharField(max_length=40)
    activa = models.BooleanField(default=True)

    class Meta:
        db_table = "cuentas_corrientes"
        verbose_name = "Cuenta corriente"
        verbose_name_plural = "Cuentas corrientes"
        ordering = ["banco__nombre", "numero", "id"]

    @property
    def cheques_a_pagar(self):
        """Total a pagar en cheques de esta cuenta corriente."""
        if hasattr(self, "_a_pagar_anotado"):
            return self._a_pagar_anotado or Decimal("0")
        total = self.cheques.filter(cobrado=False).aggregate(t=Sum("importe"))["t"]
        return total or Decimal("0")

    def __str__(self):
        return f"{self.banco} - {self.numero}"


class Cheque(models.Model):
    """Cheque a pagar de una cuenta corriente.

    Cuelga de una cuenta corriente, de la que se derivan el banco y la empresa. Un
    cheque siempre es plata que sale (la empresa no recibe cheques como cobro): el
    total a pagar de la cuenta (y de la empresa) es la suma de sus importes.

    El cheque vence 30 dias despues de su fecha de cobro: pasado ese plazo ya no se
    puede cobrar (ver vencido). El plazo de 30/60/90 dias es solo una ayuda del alta
    para calcular la fecha de cobro; lo que se guarda es la fecha, no el plazo.

    'cobrado' marca que la plata ya salio: un cheque cobrado deja de contar en el
    total a pagar de la cuenta y de la empresa (esos totales suman solo los
    pendientes, cobrado=False).
    """
    DIAS_VENCIMIENTO = 30

    cuenta_corriente = models.ForeignKey(CuentaCorriente, on_delete=models.CASCADE, related_name="cheques",
                                         db_column="id_cuenta_corriente")
    """
    Numero impreso del cheque. Texto y no entero: puede tener ceros a la izquierda
    que hay que conservar. default="" para los cheques ya cargados sin numero.
    """
    numero = models.CharField(max_length=20, default="")
    # default y no auto_now_add: la fecha que vale es la del cheque, no la de la carga
    fecha_emision = models.DateField(default=timezone.localdate)
    fecha_cobro = models.DateField()
    # En concepto de que se emite el cheque
    concepto = models.CharField(max_length=250)
    # Importe en pesos
    importe = models.DecimalField(max_digits=15, decimal_places=2)
    # La plata ya salio: no cuenta mas en el total a pagar (pendientes)
    cobrado = models.BooleanField(default=False)

    class Meta:
        db_table = "cheques"
        verbose_name = "Cheque"
        verbose_name_plural = "Cheques"
        # Los mas proximos a cobrar primero; el id desempata los del mismo dia
        ordering = ["fecha_cobro", "id"]

    @property
    def vencimiento(self):
        # Ultimo dia en que el cheque se puede cobrar: 30 dias despues de la fecha de cobro
        return self.fecha_cobro + timedelta(days=self.DIAS_VENCIMIENTO)

    @property
    def vencido(self):
        # Ya paso el plazo de cobro: nadie lo puede cobrar mas
        return timezone.localdate() > self.vencimiento

    def __str__(self):
        return f"Cheque de {self.importe} ({self.cuenta_corriente})"


