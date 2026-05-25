{{/* Subchart fullname is "release-mainframe" so resources stay disambiguated. */}}
{{- define "mainframe.fullname" -}}
{{- printf "%s-mainframe" .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "mainframe.labels" -}}
app.kubernetes.io/name: mainframe
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/component: mainframe-bridge
{{- end -}}

{{/* Resolves the api image whether passed by parent or set on the subchart. */}}
{{- define "mainframe.image" -}}
{{- $repo := .Values.image.repository -}}
{{- $tag := default .Chart.AppVersion .Values.image.tag -}}
{{- printf "%s:%s" $repo $tag -}}
{{- end -}}
