{{- define "omnix.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "omnix.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
{{- end -}}

{{- define "omnix.api.image" -}}
{{- $r := .Values.global.image.registry -}}
{{- $repo := .Values.api.image.repository -}}
{{- $tag := default .Chart.AppVersion .Values.api.image.tag -}}
{{- printf "%s/%s:%s" $r $repo $tag -}}
{{- end -}}

{{- define "omnix.worker.image" -}}
{{- $r := .Values.global.image.registry -}}
{{- $repo := .Values.worker.image.repository -}}
{{- $tag := default .Chart.AppVersion .Values.worker.image.tag -}}
{{- printf "%s/%s:%s" $r $repo $tag -}}
{{- end -}}

{{- define "omnix.studio.image" -}}
{{- $r := .Values.global.image.registry -}}
{{- $repo := .Values.studio.image.repository -}}
{{- $tag := default .Chart.AppVersion .Values.studio.image.tag -}}
{{- printf "%s/%s:%s" $r $repo $tag -}}
{{- end -}}

{{- define "omnix.verifier.image" -}}
{{- $r := .Values.global.image.registry -}}
{{- $repo := .Values.verifier.image.repository -}}
{{- $tag := default .Chart.AppVersion .Values.verifier.image.tag -}}
{{- printf "%s/%s:%s" $r $repo $tag -}}
{{- end -}}

{{/* Compose the Trillian MySQL URI for Rekor's logserver / logsigner sidecars. */}}
{{- define "omnix.rekor.trillianMysqlUri" -}}
{{- $cfg := .Values.rekor.trillian.externalMysql -}}
{{- if $cfg.host -}}
trillian:trillian@tcp({{ $cfg.host }}:{{ $cfg.port }})/{{ $cfg.database }}
{{- else -}}
trillian:trillian@tcp({{ include "omnix.fullname" . }}-rekor-mysql:3306)/trillian
{{- end -}}
{{- end -}}
