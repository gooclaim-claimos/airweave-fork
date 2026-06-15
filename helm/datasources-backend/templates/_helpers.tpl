{{- define "datasources-backend.name" -}}
{{ .Values.name | default "datasources-backend" }}
{{- end -}}

{{- define "datasources-backend.fullname" -}}
{{ include "datasources-backend.name" . }}
{{- end -}}

{{- define "datasources-backend.labels" -}}
app.kubernetes.io/name: {{ include "datasources-backend.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: datasources
app.kubernetes.io/component: backend
{{- end -}}

{{- define "datasources-backend.selectorLabels" -}}
app.kubernetes.io/name: {{ include "datasources-backend.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "datasources-backend.serviceAccountName" -}}
{{ include "datasources-backend.name" . }}
{{- end -}}
