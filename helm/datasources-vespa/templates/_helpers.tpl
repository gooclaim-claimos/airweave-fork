{{- define "datasources-vespa.name" -}}
datasources-vespa
{{- end -}}

{{- define "datasources-vespa.labels" -}}
app.kubernetes.io/name: {{ include "datasources-vespa.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: datasources
{{- end -}}

{{- define "datasources-vespa.selectorLabels" -}}
app.kubernetes.io/name: {{ include "datasources-vespa.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
