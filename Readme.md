# TTS Clipboard MP3 🎙️

**Conversão de texto colado em leitura por voz ou MP3 (Português)**

Aplicação desktop em Python que permite **colar um texto**, **ouvir imediatamente** (offline) ou **gerar um arquivo MP3**, usando diferentes motores de TTS, com foco em **textos longos**, controle de execução e versionamento rigoroso.

Projeto desenvolvido no contexto educacional e experimental do **Espaço CMaker**.

---

## ✨ Funcionalidades

* 📋 **Texto via Ctrl+C / Ctrl+V**
* 🔊 **LER AGORA** (sem gerar MP3 – offline via `pyttsx3`)
* 🎧 **GERAR MP3**

  * Edge TTS (voz neural, rate e pitch)
  * gTTS (fallback automático)
* 🧩 **Textos grandes**

  * Divisão em blocos (chunks)
  * Concatenação automática
* ⏯️ **Controle de execução**

  * Pausar / Continuar
  * Parar (com reinicialização do motor)
* 📊 **Barra de progresso + percentual**
* ⚙️ **Configurações persistentes**
* 📝 **Versionamento com changelog**
* 🖥️ Interface gráfica em Tkinter (Windows/Linux)

---

## ⚠️ Nota importante (versão atual)

A versão **v0.6.6 [ESTÁVEL]** possui um **problema conhecido**:

> As configurações de **voz / rate / pitch / backend**
> **não estão sendo aplicadas corretamente ao gerar MP3**,
> apenas no **LER AGORA**.

Esse problema está **documentado no CHANGELOG** e será corrigido em versão futura.

---

## 🧠 Arquitetura resumida

* **LER AGORA**

  * `pyttsx3`
  * Offline
  * Configurações aplicadas corretamente
* **GERAR MP3**

  * Preferencial: `edge-tts`
  * Fallback: `gTTS`
  * Divide texto → gera MP3s parciais → concatena

---

## 📦 Requisitos

### Python

* Python **3.10+** (recomendado)

### Bibliotecas

```bash
pip install pyttsx3 gtts edge-tts
```

### FFmpeg (recomendado)

Usado para concatenação rápida de MP3.

#### Windows

```bash
winget install Gyan.FFmpeg
```

> Sem FFmpeg o programa funciona, mas usa concatenação simples (menos confiável).

---

## 🚀 Como usar

1. Clone o repositório:

```bash
git clone https://github.com/Espaco-CMaker/tts-clipboard-mp3.git
cd tts-clipboard-mp3
```

2. Execute:

```bash
python main.py
```

3. Cole o texto no editor
4. Escolha:

   * **LER AGORA**
   * **GERAR MP3**

---

## 📂 Estrutura

```
.
├── main.py
├── config_tts_clipboard_mp3.json
├── saida_mp3/
├── README.md
```

---

## 🧾 CHANGELOG (resumo)

* **v0.6.6 [ESTÁVEL]**

  * Barra de progresso e %
  * Controle PAUSAR / PARAR
  * Reinício automático do motor
  * ⚠️ Limitação conhecida no MP3
* **v0.6.4**

  * Recuperação robusta após cancelamento
* **v0.4.0 [ESTÁVEL]**

  * Primeira versão utilizável

> Cada versão registra o **número total de linhas do programa**
> e é **corrigido na interação seguinte**, conforme regra do projeto.

---

## 👨‍🏫 Sobre o autor

**Fábio Bettio**
Professor, Engenheiro de Computação, Mestre em Educação
Fundador do **Espaço CMaker**

Atua com:

* Educação Maker
* Robótica educacional
* IoT e Sistemas Ciberfísicos
* Formação de professores
* Projetos educacionais com impacto social

---

## 🏭 Espaço CMaker

O **Espaço CMaker** é um laboratório Maker independente focado em:

* Aprendizagem baseada em projetos
* Cultura Maker
* Prototipagem digital
* Robótica e programação
* Formação docente e educação tecnológica

🌐 **Site:** [https://cmaker.com.br](https://cmaker.com.br)

---

## 📄 Licença

Uso **educacional e experimental**.
Sinta-se livre para estudar, adaptar e evoluir o projeto.

---

Se quiser, no próximo passo eu:

* adiciono **LOG persistente em arquivo**
* estruturo **aba LOG + aba SOBRE no código**
* ou preparo **issues padrão** para o GitHub (bug, feature, roadmap).
