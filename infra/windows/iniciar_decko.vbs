' iniciar_decko.vbs — sobe a API do piloto e o túnel quando o Windows entra.
'
' A cópia que o Windows executa fica em:
'   %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\iniciar_decko.vbs
' Esta aqui é a versão versionada; a de lá é cópia. Alterou uma, copie para a outra.
'
' Por que VBScript e não .bat: o .bat abre janela de console, e fechá-la sem querer mata
' os dois processos. O WScript.Shell sobe oculto e sem bloquear o login.
'
' ---------------------------------------------------------------- o que ele NÃO resolve
'
' O túnel rápido (`--url`, sem conta) ganha uma URL ALEATÓRIA a cada partida. Como a tela
' da Vercel leva a URL da API embutida no pacote montado, toda reinicialização quebra o
' front até um build novo. Para piloto com cliente, isso não serve.
'
' A saída é o túnel NOMEADO, que mantém o mesmo domínio para sempre. O script usa ele
' automaticamente assim que existir — basta rodar uma vez, com conta na Cloudflare:
'
'   cloudflared tunnel login
'   cloudflared tunnel create decko
'   cloudflared tunnel route dns decko api.seudominio.com.br
'
' Enquanto isso não existe, o script cai no túnel rápido e grava a URL do dia em
' url-do-tunel.txt, na pasta de registros — senão não há como descobrir qual é.

Option Explicit

Const OCULTO = 0
Const NAO_ESPERAR = False
Const LER = 1

Const RAIZ = "E:\Projetos\decko"
Const PORTA = 8000
Const TUNEL_NOMEADO = "decko"
Const SEGUNDOS_PARA_A_API = 90

Dim shell, fso, pastaDeLogs, logDaApi, logDoTunel, arquivoDaUrl, credencialDoTunel

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

pastaDeLogs = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Decko\logs"
GarantirPasta pastaDeLogs

logDaApi = pastaDeLogs & "\api.log"
logDoTunel = pastaDeLogs & "\tunel.log"
arquivoDaUrl = pastaDeLogs & "\url-do-tunel.txt"

' Registro novo a cada partida: log que só cresce vira inútil na primeira semana.
ApagarSeExistir logDaApi
ApagarSeExistir logDoTunel

' ---------------------------------------------------------------- 1. a API

shell.Run "cmd /c cd /d """ & RAIZ & """ && uv run --env-file .env.piloto uvicorn " & _
          "decko.main:app --host 127.0.0.1 --port " & PORTA & _
          " >> """ & logDaApi & """ 2>&1", OCULTO, NAO_ESPERAR

' Espera a API dizer que subiu, em vez de contar três segundos no escuro.
'
' Três segundos é chute: numa máquina fria, com o Windows ainda abrindo o resto do login,
' o Python demora mais que isso — e aí o túnel subiria apontando para porta vazia.
If Not EsperarPorTexto(logDaApi, "Application startup complete", SEGUNDOS_PARA_A_API) Then
    Registrar logDaApi, vbCrLf & "[iniciar_decko] a API não subiu em " & _
        SEGUNDOS_PARA_A_API & "s — túnel não foi iniciado."
    WScript.Quit 1
End If

' ---------------------------------------------------------------- 2. o túnel

credencialDoTunel = shell.ExpandEnvironmentStrings("%USERPROFILE%") & _
                    "\.cloudflared\" & TUNEL_NOMEADO & ".json"

If fso.FileExists(credencialDoTunel) Then
    ' Túnel nomeado: domínio fixo, a tela da Vercel continua valendo entre reinicializações.
    shell.Run "cmd /c cloudflared tunnel run --url http://127.0.0.1:" & PORTA & _
              " " & TUNEL_NOMEADO & " >> """ & logDoTunel & """ 2>&1", OCULTO, NAO_ESPERAR
    Registrar arquivoDaUrl, "Túnel nomeado '" & TUNEL_NOMEADO & "' — domínio fixo." & vbCrLf & _
                            "Veja o domínio com: cloudflared tunnel route dns list"
Else
    shell.Run "cmd /c cloudflared tunnel --url http://127.0.0.1:" & PORTA & _
              " --no-autoupdate >> """ & logDoTunel & """ 2>&1", OCULTO, NAO_ESPERAR

    ' A URL é sorteada agora; sem gravar, não há como descobrir qual saiu.
    Dim url
    url = EsperarPelaUrl(logDoTunel, 60)
    If url = "" Then
        Registrar arquivoDaUrl, "O túnel não publicou URL. Veja " & logDoTunel
    Else
        Registrar arquivoDaUrl, url & vbCrLf & vbCrLf & _
            "URL TEMPORÁRIA: muda a cada reinicialização." & vbCrLf & _
            "A tela publicada precisa de build novo com VITE_API_URL=" & url & vbCrLf & _
            "Para parar de mudar, crie o túnel nomeado — ver o cabeçalho deste script."
    End If
End If

' ---------------------------------------------------------------- auxiliares

Sub GarantirPasta(caminho)
    Dim pai
    If fso.FolderExists(caminho) Then Exit Sub
    pai = fso.GetParentFolderName(caminho)
    If Not fso.FolderExists(pai) Then fso.CreateFolder pai
    fso.CreateFolder caminho
End Sub

Sub ApagarSeExistir(caminho)
    If fso.FileExists(caminho) Then fso.DeleteFile caminho, True
End Sub

Sub Registrar(caminho, texto)
    Dim saida
    Set saida = fso.OpenTextFile(caminho, 8, True)
    saida.WriteLine texto
    saida.Close
End Sub

Function LerTudo(caminho)
    Dim entrada
    LerTudo = ""
    If Not fso.FileExists(caminho) Then Exit Function
    On Error Resume Next
    Set entrada = fso.OpenTextFile(caminho, LER, False)
    If Err.Number = 0 Then
        LerTudo = entrada.ReadAll
        entrada.Close
    End If
    On Error GoTo 0
End Function

Function EsperarPorTexto(caminho, procurado, segundos)
    Dim i
    EsperarPorTexto = False
    For i = 1 To segundos * 2
        If InStr(LerTudo(caminho), procurado) > 0 Then
            EsperarPorTexto = True
            Exit Function
        End If
        WScript.Sleep 500
    Next
End Function

' Pesca o https://....trycloudflare.com que o cloudflared imprime na caixa de boas-vindas.
Function EsperarPelaUrl(caminho, segundos)
    Dim i, re, achados
    Set re = New RegExp
    re.Pattern = "https://[a-z0-9-]+\.trycloudflare\.com"
    re.IgnoreCase = True
    re.Global = False

    EsperarPelaUrl = ""
    For i = 1 To segundos * 2
        Set achados = re.Execute(LerTudo(caminho))
        If achados.Count > 0 Then
            EsperarPelaUrl = achados(0).Value
            Exit Function
        End If
        WScript.Sleep 500
    Next
End Function
