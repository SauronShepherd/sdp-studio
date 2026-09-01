{{- define "sdpstudio.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- define "sdpstudio.fullname" -}}
{{- printf "%s-%s" .Release.Name (include "sdpstudio.name" .) | trunc 63 | trimSuffix "-" }}
{{- end }}
