{{- define "microshop.namespace" -}}
{{- default .Release.Namespace .Values.namespaceOverride -}}
{{- end -}}

{{- define "microshop.databaseEnv" -}}
{{- $svc := .service -}}
{{- if $svc.database }}
- name: POSTGRES_DB
  value: {{ $svc.database.name | quote }}
- name: POSTGRES_USER
  value: {{ $svc.database.user | quote }}
- name: POSTGRES_PASSWORD
  valueFrom:
    secretKeyRef:
      name: microshop-secret
      key: {{ $svc.database.passwordSecretKey | quote }}
{{- end }}
{{- end -}}
