# Validación de entradas

## Puesta en marcha

Reconstruir la imagen y aplicar las migraciones incluidas:

```powershell
docker compose up --build -d
docker compose exec web python manage.py migrate
```

Las migraciones `tickets.0005_admission_tickets_and_refunds` y
`tickets.0006_purchase_validation_credential` conservan las butacas y las fechas de
uso registradas, y agregan una credencial única a cada compra anterior. Las funciones
ya canceladas reciben su devolución simulada y aviso persistente, sin enviar correo
durante la migración. No se regeneran códigos al editar o volver a consultar una compra.

Las migraciones históricas del proyecto conservan los nombres de modelos en español;
la nueva migración referencia esos modelos históricos y las mismas tablas que usan
los modelos actuales en inglés. No elimina ni recrea las tablas existentes.

## Operación

1. El gerente entra a **Usuarios → Editar usuario** y activa **Operador de entradas**.
   También se puede crear el perfil en **Admin → Operadores**. No necesita `is_staff`
   ni permisos del admin. El rol Acomodador existente se conserva separado.
2. El operador inicia sesión y llega a **Validar entradas**, la única pestaña de su
   panel. El gerente también puede validar. Los controles de autorización se aplican
   tanto a GET como a POST, incluso si se ingresa directamente a una URL de gestión.
3. Elige la función y consulta una entrada mediante cámara, imagen o código manual.
   La cámara requiere HTTPS (o localhost). El lector jsQR se sirve desde los estáticos
   de la aplicación; las imágenes se procesan en el navegador.
4. Comprueba película, sala, horario y butaca, y presiona **Confirmar ingreso**.
   La consulta del código nunca consume la entrada: solamente la confirmación por POST.

El cliente encuentra un detalle expandible y un único botón **Ver QR de la compra**
en **Mis entradas**. Si usa dos entradas de una compra de cuatro, las otras dos
continúan disponibles y el mismo QR sigue representando el saldo de la compra.

Se admite una entrada de la función seleccionada si está publicada y todavía no
terminó. Se permite el ingreso antes del comienzo, sin una ventana horaria mínima.
Las funciones ocultas, finalizadas, canceladas y las compras devueltas no permiten ingreso.

## Código y concurrencia

El QR contiene `BC2:` seguido de 32 caracteres generados con `secrets.token_urlsafe(24)`:
192 bits aleatorios por compra, con unicidad en base de datos. No contiene IDs de
compra, datos personales ni una URL con credenciales. El prefijo versiona el formato.
El código se guarda para volver a mostrar el mismo QR; no depende de `SECRET_KEY`.

El QR se genera en el navegador cuando el comprador abre el detalle. No se guarda ni se
solicita una imagen de QR al servidor. El cliente también ve una referencia breve de seis caracteres para reconocer la compra.
No es el secreto del QR y solo se acepta junto a la función seleccionada por el operador.
Un hash de un ID secuencial sería predecible; el QR usa una credencial aleatoria.
Las páginas y las imágenes QR exigen que el usuario sea el comprador y responden
con `Cache-Control: no-store`. El operador envía el código por POST y no por la URL.

Validación, compra y cancelación toman primero un bloqueo sobre la función en
PostgreSQL. La validación bloquea la compra y las unidades pendientes que consume,
y registra fecha y operador: dos lectores simultáneos no pueden autorizar más entradas
de las disponibles. Las compras, entradas y devoluciones son de solo consulta en Admin;
la antigua acción masiva de marcar asientos se reemplaza por el flujo de validación.

## Cancelación y notificaciones

Cancelar una función registra, en la misma transacción, una devolución simulada por
el total de cada compra, incluso si parte de sus entradas ya se utilizó. Cada devolución
tiene referencia única y un aviso permanente en **Mis entradas**. No se mueve dinero
real. Las reservas pendientes se liberan y todas las entradas quedan inhabilitadas.

Después del commit se intenta enviar un correo por compra. Si falla el backend,
la cancelación y el aviso en la aplicación se conservan. Se pueden reintentar los correos
pendientes (también los correspondientes a cancelaciones anteriores a la migración):

```powershell
docker compose exec web python manage.py send_refund_notifications
```

Puede programarse ese comando periódicamente en el hosting. El envío SMTP puede
repetirse si el proveedor aceptó el correo pero la conexión falló antes de confirmarlo;
la devolución en base de datos siempre es única.

En desarrollo los emails se imprimen en consola. Para entrega real, configurar
`DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend` y las variables
`DJANGO_EMAIL_*` / `DJANGO_DEFAULT_FROM_EMAIL` documentadas en `.env.example`.

## Tests incluidos (no ejecutados durante la implementación)

```powershell
docker compose exec web python manage.py test domain.tickets.test_admission
docker compose exec web python manage.py test
```

Cubren la credencial por compra, validación parcial, saldo agotado, función incorrecta,
propiedad del QR, permisos, asignación de operadores y devoluciones simuladas.

Comprobación manual: generar una compra de cuatro, ampliar su único QR desde un celular,
leerlo desde otro dispositivo, confirmar el ingreso de dos personas y comprobar que las
otras dos siguen disponibles. Repetir una lectura y después cancelar la función para verificar
el rechazo de los QR restantes y el aviso de devolución.
