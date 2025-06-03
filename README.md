# Ayudante Sintaxis

Este repositorio contiene un ejemplo de asistente de correcci\xc3\xb3n de trabajos pr\xc3\xa1cticos (TP) implementado en Python. El script `mcp_email_assistant.py` se conecta a Gmail para buscar el correo m\xc3\xa1s reciente con un adjunto en formato ZIP, extrae el archivo y verifica la presencia de los TADs solicitados. Luego genera un reporte y responde al remitente con el resultado.

Para usarlo se deben generar las credenciales OAuth de Gmail y guardar el archivo `token.json` obtenido de la autorizaci\xc3\xb3n previa. Los paquetes necesarios se encuentran en `requirements.txt`.

Este ejemplo puede integrarse en flujos de automatizaci\xc3\xb3n como n8n.
