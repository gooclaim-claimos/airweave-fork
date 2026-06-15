{{- define "datasources-frontend.name" -}}
{{ .Values.name | default "datasources-frontend" }}
{{- end -}}

{{- define "datasources-frontend.labels" -}}
app.kubernetes.io/name: {{ include "datasources-frontend.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: datasources
app.kubernetes.io/component: frontend
{{- end -}}

{{- define "datasources-frontend.selectorLabels" -}}
app.kubernetes.io/name: {{ include "datasources-frontend.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "datasources-frontend.serviceAccountName" -}}
{{ include "datasources-frontend.name" . }}
{{- end -}}
