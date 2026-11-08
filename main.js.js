async function sendMessage(text) {
    if (!text.trim()) return;
    appendMessage("Sohil Boss", text);
    inputField.value = "";

    try {
        const response = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: text })
        });
        const data = await response.json();
        appendMessage("Zoya", data.response);
        speakText(data.response);
    } catch (err) {
        const errTxt = "Server connect hone me error aaya.";
        appendMessage("Zoya", errTxt);
        speakText(errTxt);
    }
}