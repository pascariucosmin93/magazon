{{- define "microshop.namespace" -}}
{{- default .Release.Namespace .Values.namespaceOverride -}}
{{- end -}}
