from datetime import date
from decimal import Decimal

from django.db import models
from django.db.models import Sum, F, Subquery, OuterRef, DecimalField, Value
from django.db.models.functions import Coalesce
from django.utils import timezone


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
        # Si el queryset vino anotado con con_totales(), uso el valor ya calculado
        # para no disparar una query por cada operacion del listado.
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
    # Una linea de la operacion apunta a un producto envasado (venta por unidad) O a un
    # articulo de cotizaciones (venta/compra a granel en kilos), nunca a los dos a la vez.
    # La exclusion mutua la garantiza el CheckConstraint de abajo.
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, db_column="id_producto",
                                 null=True, blank=True)
    cotizacion = models.ForeignKey("Cotizaciones", on_delete=models.PROTECT, db_column="id_cotizacion",
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
        # Nombre unico para mostrar en listados, remito y detalle de operacion,
        # sin que cada template tenga que ramificar entre producto y cotizacion
        if self.es_granel:
            return f"{self.cotizacion.articulo} (granel)"
        return self.producto.nombre

    def __str__(self):
        return f"{self.cantidad} de {self.nombre_item} (Op: {self.operacion.id})"


class Pago(models.Model):
    operacion = models.ForeignKey(Operacion, on_delete=models.CASCADE, db_column="id_operacion")
    # default (y no auto_now_add) para que el pago automatico de una operacion
    # "contado" con fecha vieja pueda llevar esa misma fecha
    fecha = models.DateTimeField(default=timezone.now)
    monto = models.DecimalField(max_digits=15, decimal_places=2)

    class Meta:
        db_table = "pagos"
        verbose_name_plural = "Pagos"

    def __str__(self):
        return f"Pago de la operacion: {self.operacion}"


class Cotizaciones(models.Model):
    articulo = models.CharField(max_length=25, unique=True)
    monto = models.PositiveIntegerField(default=1)
    # Kilos disponibles a granel del articulo. Uso Decimal (no Float) para evitar
    # ruido de precision al acumular pesadas fraccionadas, igual que DetalleOperacion
    cantidad = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        db_table = "cotizaciones"
        verbose_name_plural = "Cotizaciones"

    def __str__(self):
        return f"Cotizacion {self.articulo}: {self.monto}"


class Empleado(models.Model):
    nombre = models.CharField(max_length=25)
    apellido = models.CharField(max_length=25)
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
        # Cantidad de viajes activos del empleado, sumando los tres tipos de viaje
        # (miel/cera, reparto y cereal). Un viaje cuenta como uno, sin importar
        # cuantos destinos tenga. Si el queryset vino anotado con _num_viajes
        # (ver obtener_empleados_activos) reutilizo ese valor para evitar una
        # query por fila en el listado de flota.
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
    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE, db_column="id_empleado")
    fecha = models.DateField(default=timezone.now)
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    observaciones = models.CharField(max_length=250, blank=True, default="")

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
        # Suma los tres tipos de viaje activos (miel/cera, reparto y cereal),
        # igual que en Empleado.
        if hasattr(self, "_num_viajes"):
            return self._num_viajes
        return (
            self.viaje_set.filter(activo=True).count()
            + self.viajereparto_set.filter(activo=True).count()
            + self.viajecereal_set.filter(activo=True).count()
        )

    def __str__(self):
        return f"Vehiculo {self.nombre} ({self.patente})"


class Viaje(models.Model):
    empleado = models.ForeignKey(Empleado, on_delete=models.PROTECT, db_column="id_empleado")
    vehiculo = models.ForeignKey(Vehiculo, on_delete=models.PROTECT, db_column="id_vehiculo")
    inicio_caja = models.PositiveIntegerField(default=0)
    fecha_inicio = models.DateField()
    fecha_vuelta = models.DateField(null=True, blank=True)
    activo = models.BooleanField(default=True)

    @property
    def total_gastos(self) -> int:
        from django.db.models import Sum

        # Suma todos los montos de la tabla Gasto asociados a este viaje
        resultado = self.detalle_gastos.aggregate(total=Sum('monto'))['total']
        if resultado is not None:
            return resultado
        else:
            return 0

    @property
    def final_caja(self) -> int:
        return int(self.inicio_caja) - self.total_gastos

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

    class Meta:
        abstract = True


class Gasto(GastoBase):
    # Para los viajes de miel/cera, la nombre gasto simplemente
    viaje = models.ForeignKey(Viaje, on_delete=models.CASCADE, related_name="detalle_gastos", db_column="id_viaje")

    class Meta:
        db_table = "gastos"

    def __str__(self):
        return f"Gasto {self.gasto} de {self.monto} pesos (Viaje: {self.viaje})"


class ViajeReparto(models.Model):
    fecha_viaje_reparto = models.DateField()
    empleado = models.ForeignKey(Empleado, on_delete=models.PROTECT, db_column="id_empleado")
    vehiculo = models.ForeignKey(Vehiculo, on_delete=models.PROTECT, db_column="id_vehiculo")
    # Localidad del reparto, elegida del catalogo. Es nullable solo para los repartos
    # historicos que se cargaron con destinos escritos a mano y quedaron sin catalogo.
    # Referencia por texto porque el catalogo se declara mas abajo en este mismo archivo.
    destino = models.ForeignKey("DestinoViajeReparto", on_delete=models.PROTECT, null=True, blank=True,
                                db_column="id_destino", related_name="viajes")
    gasto_combustible_viaje_reparto = models.PositiveIntegerField(default=0)
    costo_empleado = models.PositiveIntegerField(default=0)
    valor_viaje = models.PositiveIntegerField(default=0)
    activo = models.BooleanField(default=True)
    pagado = models.BooleanField(default=False)
    # Momento en que se registro el cobro. Queda en None mientras el viaje esta
    # impago y se limpia si el cobro se da de baja, asi nunca muestra una fecha
    # que no corresponde al estado actual.
    fecha_pago = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "viaje_reparto"

    @property
    def total_gastos(self) -> int:
        # Suma de los gastos extra cargados a este viaje de reparto (tabla hija).
        # Si el viaje no tiene gastos, aggregate devuelve None y lo normalizo a 0.
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
    valor_viaje = models.PositiveIntegerField(default=0)
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
    # Cliente al que se le presta el flete. Es nullable para no romper los viajes
    # de cereal que ya existian antes de incorporar este campo (quedan "Sin cliente").
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, null=True, blank=True,
                                db_column="id_cliente", related_name="viajes_cereales")
    tipo_cereal = models.CharField(max_length=50, choices=cereales)
    # El CTG es un codigo de hasta 15 digitos que puede tener ceros a la izquierda, por eso
    # lo guardo como texto: un IntegerField perderia esos ceros (00123456 -> 123456)
    codigo_trazabilidad_granos = models.CharField(max_length=15)
    # Toneladas transportadas. Uso Decimal (no Integer/Float) para admitir hasta dos
    # decimales sin el ruido de precision del punto flotante, igual que en el resto de
    # las cantidades comerciales del sistema (DetalleOperacion, Cotizaciones).
    toneladas = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    precio_tonelada = models.PositiveIntegerField(default=0)
    porcentaje_empleado = models.PositiveIntegerField(default=0)
    activo = models.BooleanField(default=True)
    pagado = models.BooleanField(default=False)
    # Momento en que se registro el cobro. Queda en None mientras el viaje esta
    # impago y se limpia si el cobro se da de baja, asi nunca muestra una fecha
    # que no corresponde al estado actual.
    fecha_pago = models.DateTimeField(null=True, blank=True)

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
        # Suma de todos los gastos cargados a este viaje de cereal. Si el viaje no
        # tiene gastos, aggregate devuelve None y lo normalizo a 0.
        resultado = self.detalle_gastos.aggregate(total=Sum('monto'))['total']
        return resultado if resultado is not None else 0

    @property
    def subtotal(self):
        # Base sobre la que se reparte el empleado: facturacion menos los gastos del viaje
        return self.total_bruto - self.total_gastos

    @property
    def pago_empleado(self):
        # Lo que se lleva el empleado segun su porcentaje sobre el subtotal (bruto - gastos).
        # Si los gastos superan al bruto el subtotal es negativo; en ese caso el empleado no
        # "aporta" plata, asi que tomo la base en 0 para no calcular un pago negativo.
        base = self.subtotal if self.subtotal > 0 else 0
        return base * self.porcentaje_empleado / 100

    @property
    def ganancia_neta(self):
        # Lo que le queda a la empresa: el subtotal (ya descontados los gastos) menos
        # la parte del empleado. Puede ser negativo si los gastos superan la facturacion.
        return self.subtotal - self.pago_empleado

    def __str__(self):
        return f"Viaje de cereal nro: {self.id}"


class DetalleViajeCereal(models.Model):
    viaje_cereal = models.ForeignKey(ViajeCereal, on_delete=models.CASCADE,
                                     related_name="destinos", db_column="id_viajecereal")
    destino = models.CharField(max_length=30)

    class Meta:
        db_table = "detalle_viaje_cereal"

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

    Todo el modulo de alquileres identifica un mes por su dia 1: asi el periodo
    entra en un DateField comun, se ordena y se compara sin trucos, y "julio de
    2026" es siempre el mismo valor lo escriba quien lo escriba.
    """
    hoy = timezone.localdate()
    return date(hoy.year, hoy.month, 1)


class CasaQuerySet(models.QuerySet):
    def con_pago_del_mes(self, periodo=None):
        """Anota cuanto se cobro de cada casa en el periodo pedido (por defecto, el mes en curso).

        Sin esto, pintar el estado de cada fila del listado dispara una query por
        casa (el mismo N+1 que evita Operacion.con_totales).

        Un mes tiene a lo sumo un pago, asi que la suma devuelve ese unico monto
        y el cero significa que todavia no se cobro. Sumo en vez de preguntar si
        existe porque el listado tambien muestra cuanto entro, no solo si entro.
        """
        periodo = periodo or periodo_actual()
        pagos_periodo = (
            PagoAlquiler.objects.filter(casa=OuterRef("pk"), periodo=periodo)
            .values("casa")
            .annotate(total=Sum("monto"))
            .values("total")
        )
        return self.annotate(
            _pagado_periodo_anotado=Coalesce(
                Subquery(pagos_periodo, output_field=DecimalField()),
                Value(0),
                output_field=DecimalField(),
            ),
        )


class Casa(models.Model):
    """Propiedad que la empresa da en alquiler.

    Ningun dato es obligatorio: una casa se puede dar de alta con el nombre solo
    y completarse despues, asi que todos los campos admiten null menos los dos
    booleanos, que siempre tienen un valor definido.
    """
    objects = CasaQuerySet.as_manager()

    nombre = models.CharField(max_length=60, null=True, blank=True)
    localidad = models.CharField(max_length=60, null=True, blank=True)
    direccion = models.CharField(max_length=120, null=True, blank=True)
    # Alquiler mensual pactado. Es el valor con el que se compara lo cobrado del
    # mes para decidir si el periodo esta pago, parcial o impago.
    precio = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    # Comision de la inmobiliaria expresada en porcentaje del alquiler (0 a 100):
    # si sube el precio, la comision acompaña sola y no hay que reescribirla.
    comision_inmobiliaria = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    alquilada = models.BooleanField(default=False)
    """
    Desde cuando la casa existe para el sistema. Sin esto, cargar una casa hoy
    le inventa deuda en todos los meses anteriores, porque el estado de un mes
    pasado se reconstruye con las casas que hay ahora. Es una fecha editable y
    no un auto_now_add a proposito: si la casa se administra desde antes de
    cargarla, el usuario corrige el dato y los meses viejos cierran bien.
    """
    fecha_alta = models.DateField(default=timezone.localdate)
    activa = models.BooleanField(default=True)

    class Meta:
        db_table = "casas"
        verbose_name_plural = "Casas"
        ordering = ["nombre", "id"]

    @property
    def comision_monto(self):
        # Cuanto se lleva la inmobiliaria por mes. Sin precio cargado no hay nada
        # que calcular; sin comision cargada, la casa se administra sola y es cero.
        if self.precio is None:
            return None
        porcentaje = self.comision_inmobiliaria or Decimal("0")
        return (self.precio * porcentaje / Decimal("100")).quantize(Decimal("0.01"))

    @property
    def neto_mensual(self):
        # Lo que le queda a la empresa una vez descontada la inmobiliaria
        if self.precio is None:
            return None
        return self.precio - self.comision_monto

    @property
    def total_pagado_periodo(self):
        # Cobrado del periodo. Si el queryset vino de con_pago_del_mes() uso ese
        # valor ya calculado, que ademas es el que fija que mes se esta mirando;
        # suelto, sin anotacion, cae en el mes en curso.
        if hasattr(self, "_pagado_periodo_anotado"):
            return self._pagado_periodo_anotado or Decimal("0")
        return self.pagos.filter(periodo=periodo_actual()).aggregate(total=Sum("monto"))["total"] or Decimal("0")

    @property
    def cobrada_en_el_periodo(self):
        # El alquiler se cobra entero o no se cobra, asi que alcanza con saber si
        # hay un pago cargado en el mes: no hay monto que comparar contra el precio.
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

        El pago se pregunta primero y le gana a "alquilada". Un pago cargado es un
        hecho de ese mes; "alquilada" es el estado de hoy y sobre el pasado es una
        suposicion. Al reves, una casa que se desocupo hacia figurar sin alquilar
        un mes que en realidad habia cobrado.

        Lo que sigue sin tener historia es el precio: lo que se espera cobrar en un
        mes viejo se calcula con el precio actual. Eso se arregla con una tabla de
        contratos (casa, desde, hasta, precio), no guardando el estado mes por mes.
        """
        if self.cobrada_en_el_periodo:
            return "Cobrado"
        if not self.alquilada:
            return "Sin alquilar"
        return "Pendiente de cobro"

    def __str__(self):
        return self.nombre or f"Casa {self.id}"


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
        # "07/2026". El nombre del mes lo arma la plantilla con el filtro date,
        # aca dejo algo corto y sin depender del locale para listados y logs.
        return self.periodo.strftime("%m/%Y")

    def __str__(self):
        return f"Pago de {self.monto} del periodo {self.periodo_label} ({self.casa})"