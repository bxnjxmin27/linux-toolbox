import QtQuick
import QtQuick.Controls.Basic

Item {
    id: root
    property var filters: ({})

    Column {
        width: Math.min(560, parent.width); spacing: 22
        Text { text: "Einstellungen"; color: Theme.text; font.family: Theme.font; font.pixelSize: 24; font.weight: Font.Bold }

        FieldEditor {
            width: parent.width
            field: ({ key: "output_dir", type: "folder", label: "Ausgabeordner", hint: "Jeder Durchlauf bekommt einen eigenen, datierten Unterordner. Originale bleiben unberührt.", filter: "", options: [], placeholder: "" })
            value: backend.setting("output_dir")
            onEdited: (v) => backend.setSetting("output_dir", v)
        }
        FieldEditor {
            width: parent.width
            field: ({ key: "whisper_model", type: "choice", label: "Transkriptions-Modell", hint: "Größere Modelle sind genauer, aber langsamer. Wird beim ersten Einsatz einmalig geladen.", filter: "", placeholder: "",
                      options: [["tiny","Tiny"],["base","Base"],["small","Small"],["medium","Medium"],["large-v3","Large v3"],["large-v3-turbo","Large v3 Turbo"]] })
            value: backend.setting("whisper_model")
            onEdited: (v) => backend.setSetting("whisper_model", v)
        }
        FieldEditor {
            width: parent.width
            field: ({ key: "llm_url", type: "text", label: "Lokales Sprachmodell (Ollama) – Adresse", hint: "Für „Zusammenfassen“ und „Dokument befragen“. Nichts verlässt deinen Rechner.", filter: "", options: [], placeholder: "http://127.0.0.1:11434" })
            value: backend.setting("llm_url")
            onEdited: (v) => backend.setSetting("llm_url", v)
        }
        FieldEditor {
            width: parent.width
            field: ({ key: "llm_model", type: "text", label: "Sprachmodell", hint: "", filter: "", options: [], placeholder: "qwen3:8b" })
            value: backend.setting("llm_model")
            onEdited: (v) => backend.setSetting("llm_model", v)
        }
    }
}
