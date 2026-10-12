# FlashFood Print Agent — repositorio independiente

Código fuente extraído del proyecto Palacio del Cangrejo y preparado como repositorio separado.

## Estado

Versión de código `1.5.0` (base original `1.4.3`). Se conservan la interfaz, el emparejamiento por código, la impresión de cocina y facturas y las RPC existentes. Se corrigió el ticket de cocina para preferir `ticket_number` (evita mostrar UUID), mostrar mesa, reconocer servicio en local y leer las observaciones generales desde `observacion` además de otros campos; las notas individuales ya estaban implementadas.

**No se han generado instaladores ni se ha desplegado el repositorio en GitHub.** La versión 1.5.0 no corresponde a una versión publicada. Para actualizaciones automáticas verificadas hacen falta la URL del repositorio GitHub, un canal de Releases y artefactos firmados/validados por plataforma. No se habilitan descargas ni ejecuciones automáticas de instaladores no verificados.

## Desarrollo

```bash
python -m venv .venv
# Activar entorno virtual según SO
pip install -r requirements.txt
python agent.py
```

Configure `build_config.py` para su proyecto Supabase **sin incluir secretos privados**. `SUPABASE_ANON_KEY` es pública; nunca utilice `service_role` en el agente.

## Compilación

Revise `scripts/build-windows.bat`, `scripts/build-macos.sh` y los archivos `.spec`. Cada SO requiere su propio entorno de compilación. El instalador Windows está en `installer/windows.iss` (Inno Setup).

## Integración web

Los proyectos de restaurante **no deben copiar `agent-python`**. Mantienen el componente de configuración/monitoreo y muestran un enlace de descarga hacia las Releases del repositorio central una vez creado. Las RPC de emparejamiento e impresión siguen funcionando con la base compartida.

## Próximo requisito para actualizador

Definir `github.com/ORGANIZACION/REPOSITORIO`, permisos de publicación, firma de instaladores y estrategia de actualización por Windows/macOS/Linux. La configuración de impresoras permanece en el directorio de datos del usuario, separado de la carpeta de instalación.
