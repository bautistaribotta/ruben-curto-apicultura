from datetime import date
from decimal import Decimal

from django.db import models
from django.db.models import (Sum, F, Subquery, OuterRef, Exists, DecimalField, IntegerField,
                              DateField, Value, Q)
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
    sueldo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # Dia desde el que arranca a contar la cuenta corriente (saldo en 0). Se fija
    # solo la primera vez que se carga un sueldo; antes de ese dia no se devenga
    # sueldo ni se cuentan pagos. Null mientras el empleado no tenga cuenta.
    inicio_cuenta = models.DateField(null=True, blank=True)
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
    # Decimal porque la tarifa del catalogo puede tener centavos y el viaje se
    # queda con una copia de ese monto
    valor_viaje = models.DecimalField(max_digits=12, decimal_places=2, default=0)
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

    # --- Dadora de carga ---
    # La dadora es quien le consigue el flete al cliente. Es opcional: si el nombre
    # queda vacio, el viaje no tuvo dadora (o no le cobro). Su comision se calcula
    # sobre la facturacion (toneladas x precio), antes que los gastos: es lo primero
    # que se descuenta apenas se factura el viaje.
    COBROS_DADORA = [
        ("porcentaje", "Porcentaje"),
        ("tonelada", "Por tonelada"),
        ("efectivo", "Efectivo"),
    ]
    dadora_carga = models.CharField(max_length=60, blank=True, default="")
    # Como cobra la dadora, siempre sobre la facturacion: un porcentaje, un monto por
    # cada tonelada, o un monto fijo en efectivo. Queda vacio cuando no hay dadora.
    dadora_tipo_cobro = models.CharField(max_length=20, choices=COBROS_DADORA, blank=True, default="")
    # El valor cobrado, que se interpreta segun 'dadora_tipo_cobro': si es porcentaje
    # va de 1 a 100; si es por tonelada son los pesos por cada tonelada; si es efectivo
    # es el monto fijo. Queda en 0 cuando el viaje no tiene dadora.
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
        # Suma de todos los gastos cargados a este viaje de cereal. Si el viaje no
        # tiene gastos, aggregate devuelve None y lo normalizo a 0.
        resultado = self.detalle_gastos.aggregate(total=Sum('monto'))['total']
        return resultado if resultado is not None else 0

    @property
    def tiene_dadora(self):
        # El nombre vacio es la marca de "este viaje no tuvo dadora de carga".
        return bool(self.dadora_carga)

    @property
    def costo_dadora(self):
        # Comision de la dadora, lo primero que se descuenta de la facturacion (antes
        # que los gastos). Segun como cobre:
        #  - porcentaje: un porcentaje de la facturacion (toneladas x precio).
        #  - tonelada: una cantidad de toneladas valuadas al precio del viaje. Si la
        #    dadora se lleva "1 tonelada", cobra el precio de una tonelada de este
        #    viaje (dadora_valor toneladas x precio_tonelada).
        #  - efectivo: un monto fijo.
        # Sin dadora no hay costo.
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
        # Base sobre la que se reparte el empleado: la facturacion menos la comision
        # de la dadora (que sale primero) y menos los gastos del viaje.
        return self.total_bruto - self.costo_dadora - self.total_gastos

    @property
    def pago_empleado(self):
        # Lo que se lleva el empleado segun su porcentaje sobre el subtotal (ya
        # descontadas la dadora y los gastos). Si el subtotal es negativo tomo la base
        # en 0 para no calcular un pago negativo.
        base = self.subtotal if self.subtotal > 0 else 0
        return base * self.porcentaje_empleado / 100

    @property
    def ganancia_neta(self):
        # Lo que le queda a la empresa: el subtotal (ya descontadas dadora y gastos)
        # menos la parte del empleado. Puede ser negativo si los costos superan la
        # facturacion.
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
        # El ultimo contrato que ya habia terminado antes de este mes. Solo se usa
        # para poder decir "contrato vencido" en vez de dejar la casa muda.
        anterior = (Contrato.objects.filter(casa=OuterRef("pk"), fin__lt=periodo)
                    .order_by("-fin", "-id"))
        # Contrato corriendo HOY, que no es lo mismo que el del mes que se mira:
        # el boton de contrato carga siempre el que sigue al de hoy, asi que se
        # bloquea o no segun la fecha real y no segun el mes que este en pantalla.
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
        # Alquiler mensual del contrato de ese mes. Sin contrato no hay precio: la
        # casa no esta alquilada y no hay nada que cobrar.
        if hasattr(self, "_monto_periodo_anotado"):
            return self._monto_periodo_anotado
        contrato = self.contrato_del_periodo
        return contrato.monto_mensual if contrato else None

    @property
    def comision_inmobiliaria(self):
        # Porcentaje del alquiler (0 a 100) que se lleva la inmobiliaria. Se guarda
        # como porcentaje y no como monto para que acompañe solo a cada aumento.
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
        # Cuando termino el ultimo contrato, si es que ya termino antes de este mes.
        # Es lo que separa "se le vencio el contrato" de "nunca estuvo alquilada".
        if hasattr(self, "_fin_anterior_anotado"):
            return self._fin_anterior_anotado
        ultimo = self.contratos.filter(fin__lt=periodo_actual()).order_by("-fin", "-id").first()
        return ultimo.fin if ultimo else None

    @property
    def comision_monto(self):
        # Cuanto se lleva la inmobiliaria por mes. Sin precio cargado no hay nada
        # que calcular; sin comision cargada, la casa se administra sola y es cero.
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
        # Cobrado del periodo. Si el queryset vino de con_estado_del_mes() uso ese
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
    # default y no auto_now_add: el gasto se carga cuando se puede, no el dia que
    # se pago, y la fecha de la boleta es la que vale
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
        # "07/2026". El nombre del mes lo arma la plantilla con el filtro date,
        # aca dejo algo corto y sin depender del locale para listados y logs.
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

    def __str__(self):
        return self.nombre
