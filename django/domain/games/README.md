# Juegos

Aplicar `python manage.py migrate` y entrar a la home. La ruleta flotante abre
el modal de juegos, sin navegar. `/juegos/` redirige a la home con el modal abierto.
**Mis premios** (`/juegos/premios/`) permite seleccionar cupones y solicitar retiro.
El panel del gerente
incluye **Juegos** (`/juegos/gestion/`). Se agregan 21 preguntas iniciales y
casillas sin productos; configurar premios con productos de Candy y ampliar el
banco antes de usar en producción. No se altera la base existente automáticamente.

## Reglas e integración

- La diaria se renueva 24 horas después de iniciar una partida; no se acumula.
  Se consume antes de las extras. Solo hay una partida abierta por usuario.
- La diaria contiene hasta tres preguntas; cada trivia extra contiene una sola
  pregunta fácil y permite ganar como máximo una tirada. Consumir una extra no
  modifica la fecha de renovación de la diaria.
- Se elige una pregunta por dificultad, hasta tres. Un nivel faltante termina la
  selección. El banco vacío no consume oportunidades. Las preguntas de una
  partida son una copia inmutable; nunca se envía el índice correcto al cliente.
- Cada pregunta queda reservada globalmente durante 24 horas desde su asignación,
  incluso si el jugador no llega a responderla. Pasado ese tiempo puede volver a
  aparecer, pero nunca se repite en una misma partida. La huella del texto
  normalizado impide adelantar su reutilización importando una copia. Si todas
  están en espera se conservan las oportunidades. El panel muestra las preguntas
  disponibles ahora y conserva el historial de asignaciones.
- El tiempo por pregunta es de 10 segundos por defecto, configurable entre 1 y
  300 en Juegos → Configurar tiempo. Cada partida guarda el límite con el que
  empezó. El servidor registra como incorrectas las respuestas vencidas; cerrar,
  recargar o alternar pestañas no reinicia el reloj.
- Cada casilla tiene igual probabilidad. `count` representa repeticiones y
  `position` ordena la distribución (máximo 24 casillas activas). Los premios de
  productos inactivos o sin stock se excluyen antes de sortear. Si no quedan
  casillas, no se gasta la tirada. El resultado incluye la distribución exacta
  para animarlo, incluso si la configuración cambia después.
- Cada casilla de tirada extra se consume al ganarla para ese usuario y se
  redistribuye el resto de su ruleta. Otras cuentas conservan sus propias
  casillas; los reintentos de una operación no consumen una casilla adicional.
  “Otra trivia” está desactivada por defecto; el gerente puede activarla.
- Ganar reserva **una unidad** del stock de Candy. Canjear no descuenta otra vez.
  No hay vencimiento automático ni liberación silenciosa de premios reservados.
  El inventario del gerente muestra los cupones disponibles y canjeados.
- Ganar no genera pedidos ni QR. En **Mis premios**, el cliente selecciona hasta
  100 cupones y crea un pedido real de Candy sin cargo, con un único QR `BCC:`.
  Los cupones pasan de disponibles a solicitados y no se pueden reutilizar.
  El pedido se entrega en **Entregar candy**, con la misma cámara, código manual,
  confirmación e historial de las compras. Una entrega pasa los cupones a canjeados;
  deshacerla dentro de la ventana existente vuelve a solicitados, sin variar stock.
  Los pedidos de premios se vinculan al usuario, sin requerir compra ni función.
- Solo gerentes configuran/otorgan; gerentes y operadores canjean. Superusuario
  sin perfil de gerente conserva el comportamiento de roles del proyecto.

## JSON de preguntas

Importar agrega contenido en una transacción; exportar produce el mismo formato.
Pegar JSON o subir archivo UTF-8 de hasta 1 MB, de 1 a 500 preguntas:

```json
{"questions": [{"text": "¿Quién dirigió Jurassic Park?", "options": ["Steven Spielberg", "James Cameron", "Ridley Scott"], "correct": 0, "difficulty": 1, "active": true}]}
```

`correct`: entero 0–2. `difficulty`: entero 1 fácil, 2 media, 3 difícil.
`active`: booleano opcional, true por defecto. Pregunta de hasta 500 caracteres,
tres opciones distintas y no vacías de hasta 250 caracteres. No agregar IDs,
claves adicionales ni bloques Markdown. Se puede usar este ejemplo como formato
de salida para un LLM; revisar las respuestas antes de activar preguntas.

## Consistencia y pruebas

Las mutaciones usan transacciones y bloqueo por escritura de cuenta; las tiradas
también serializan configuración y bloquean productos en orden. Las claves UUID
de inicio, respuesta, giro, otorgamiento y pedido hacen seguros los reintentos. El cliente
retiene las claves pendientes ante fallos de conexión. El canje usa una transición
condicional del pedido pendiente → entregado: una repetición no autoriza otra entrega.
Las restricciones únicas refuerzan partidas, respuestas, tiradas y cupones.
Los eventos conservan actor, fecha y referencias, sin credenciales QR.

`python manage.py test domain.games` incluye reglas, permisos, CSRF, importación,
stock, idempotencia, canjes y peticiones simultáneas con conexiones independientes.
En SQLite, un conflicto de escritura devuelve 409 y permite reintentar; PostgreSQL
usa bloqueos de fila. La CI existente ejecuta la misma suite con PostgreSQL.
