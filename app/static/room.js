var tag_list = ["b", "i", "u", "s", "quote", "mention"];

var current_channel = 0;

var socket = io({
    auth: {
        nick: NICK,
        token: TOKEN,
    },
});

async function heartbeat() {
    await socket.emit("heartbeat", {
        nick: NICK,
        token: TOKEN,
    });
}

setInterval(() => {
    heartbeat();
}, 4000);

socket.on("connect", async () => {
    await refresh_channels();
    switch_channel(1);
});

socket.on("channel_updated", async () => {
    refresh_channels();
});

async function refresh_channels() {
    var clist = document.getElementById("channel_list");
    clist.innerHTML = "";
    var resp = await fetch("/channels", {
        headers: {
            Authorization: `Basic ${NICK} ${TOKEN}`,
        },
    });
    var channels = await resp.json();
    for (var c of channels) {
        var element = document.createElement("li");
        var lock = c["is_admin"]
            ? `<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12"><path fill="darkred" d="M0 12h11V7H4V4H3v3H2V3H1v4H0Zm1-1V8h9v3Zm1-8h1V2H2Zm2 1h3V3H4ZM3 2h5V1H3Zm4 4h3V3H9v2H8V4H7Zm1-3h1V2H8Zm0 0"/></svg>`
            : "";
        element.innerHTML = `[${c["id"]}] ${lock} ${c["name"]}`;
        element.setAttribute("style", "cursor: pointer");
        element.setAttribute("href", "#");
        element.setAttribute("id", `clist-${c["id"]}`);
        element.setAttribute("onclick", `switch_channel(${c["id"]})`);
        clist.appendChild(element);
    }
    if (current_channel != 0) {
        switch_channel(current_channel);
    }
}

socket.on("msg_deliver", async (msg) => {
    var msgbox = document.getElementById("msgbox");
    var rendered = await render_msg(msg);
    msgbox.appendChild(rendered);
    msgbox.scrollTop = msgbox.scrollHeight;
    if (!is_muted) {
        document.getElementById("msg_sfx").play();
    }
});

async function msg_send() {
    var editor = document.getElementById("editor");
    var body = editor.value;
    if (body == "") {
        window.alert("Message shouldn't be empty!");
        return;
    }
    var attachments = [];
    // Submit all attachments
    for (var key in file_buffer) {
        resp = await fetch(`/submit_upload?submit=${file_buffer[key]}`, {
            headers: {
                Authorization: `Basic ${NICK} ${TOKEN}`,
            },
        });
        if (resp.ok) {
            attachments.push(file_buffer[key]);
        }
        document.getElementById(file_buffer[key]).remove();
        delete file_buffer[key];
    }
    socket.emit("msg_send", {
        author: NICK,
        token: TOKEN,
        body: body,
        attachments: attachments,
    });
    editor.value = "";
}

var is_muted = false;

function switch_mute() {
    is_muted = !is_muted;
    if (is_muted) {
        document.getElementById(
            "mute_switch"
        ).innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="1.2em" height="1.2em" viewBox="0 0 24 24"><path fill="#000" d="M13 2h-2v2H9v2H7v2H3v8h4v2h2v2h2v2h2zM9 18v-2H7v-2H5v-4h2V8h2V6h2v12zm10-6.777h-2v-2h-2v2h2v2h-2v2h2v-2h2v2h2v-2h-2zm0 0h2v-2h-2z"/></svg>`;
    } else {
        document.getElementById(
            "mute_switch"
        ).innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="1.2em" height="1.2em" viewBox="0 0 24 24"><path fill="#000" d="M11 2H9v2H7v2H5v2H1v8h4v2h2v2h2v2h2zM7 18v-2H5v-2H3v-4h2V8h2V6h2v12zm6-8h2v4h-2zm8-6h-2V2h-6v2h6v2h2v12h-2v2h-6v2h6v-2h2v-2h2V6h-2zm-2 4h-2V6h-4v2h4v8h-4v2h4v-2h2z"/>`;
    }
}

function insert_emote(node) {
    var editor = document.getElementById("editor");
    var emote = node.value;
    var cursor = editor.selectionStart;
    editor.value =
        editor.value.slice(0, cursor) + emote + editor.value.slice(cursor);
    node.selectedIndex = 0;
}

function insert_tag(node) {
    var editor = document.getElementById("editor");
    var tag = tag_list[node.selectedIndex - 1];
    var start = editor.selectionStart;
    var end = editor.selectionEnd;
    editor.value =
        editor.value.slice(0, start) +
        `[${tag}]` +
        editor.value.slice(start, end) +
        `[/${tag}]` +
        editor.value.slice(end);
    node.selectedIndex = 0;
}

async function switch_channel(channel_id) {
    // Update Visual
    if (current_channel != 0) {
        var last_entry = document.getElementById(`clist-${current_channel}`);
        last_entry.className = "";
    }
    var current_entry = document.getElementById(`clist-${channel_id}`);
    current_entry.className = "cselected";
    current_channel = channel_id;
    // Call server update channel info
    socket.emit("sw_channel", { to: channel_id, nick: NICK, token: TOKEN });
    // Refresh messages
    var msgbox = document.getElementById("msgbox");
    msgbox.innerHTML = "";
    load_more();
    msgbox.scrollTop = msgbox.scrollHeight;
}

async function load_more(count = 30) {
    var msgbox = document.getElementById("msgbox");
    var new_msg = await fetch(
        `/messages/${current_channel}?count=${count}&offset=${msgbox.childElementCount}`,
        {
            headers: {
                Authorization: `Basic ${NICK} ${TOKEN}`,
            },
        }
    );
    var resp = await new_msg.json();
    for (var msg of resp) {
        let rendered = await render_msg(msg, msgbox);
        msgbox.insertBefore(rendered, msgbox.firstChild);
    }
}

async function render_msg(msg) {
    var attachment_ids = msg["attachments"];
    var attachments = [];
    if (attachment_ids != []) {
        for (let a of attachment_ids) {
            var resp = await fetch(`/resource_meta/${a}`);
            if (!resp.ok) {
                continue
            }
            var meta = await resp.json();
            var attach;
            if (meta["mime"].startsWith("image")) {
                attach = document.createElement("img");
                attach.style = "width: 200px";
                attach.src = `/resource/${a}`;
            }else if(meta["mime"].startsWith("video")) {
                attach = document.createElement("video");
                attach.setAttribute("controls", "")
                attach.setAttribute("width", "200")
                attach.volume = 0;
                let source = document.createElement("source");
                source.setAttribute("type", meta["mime"])
                source.setAttribute("src", `/resource/${a}`)
                attach.appendChild(source)
            } else {
                attach = document.createElement("a");
                attach.href = `/resource/${a}`;
                attach.target = "_blank";
                attach.innerText = `Download ${meta["filename"]}`;
            }
            attachments.push(attach);
        }
    }
    var msg_render = document.createElement("p");
    msg_render.id = `rendered-msg-${msg["id"]}`;
    msg_render.innerHTML = `<span style="color: red">${msg["author"]}</span> at ${msg["datetime"]} > ${msg["id"]}<br>${msg["body"]}`;
    if (attachments != []) {
        msg_render.appendChild(document.createElement("br"));
        attachments.forEach((e) => {
            msg_render.appendChild(e);
        });
    }
    return msg_render;
}

var file_buffer = {};

async function upload() {
    var file_component = document.getElementById("attachment");
    var files = file_component.files;

    if (files.length == 0) {
        window.alert("No file selected!");
        return;
    }
    var data = new FormData();
    data.append("file", files[0]);
    var fname = files[0].name;
    var response = await fetch("/index_upload", {
        method: "POST",
        body: data,
        headers: {
            Authorization: `Basic ${NICK} ${TOKEN}`,
        },
    });
    if (response.ok) {
        var uuid = (await response.json()).uuid;
        file_buffer[fname] = uuid;
        var attachment_list = document.getElementById("attachment_list");
        var attach = document.createElement("option");
        attach.id = uuid;
        attach.innerText = fname;
        attachment_list.appendChild(attach);
        window.alert(`${fname} Uploaded!`);
        file_component.value = "";
    }
}

async function delete_attach(node) {
    var deleting_name = node.value;
    node.selectedIndex = 0;
    if (window.confirm(`Are you deleting ${deleting_name} ?`)) {
        var deleting_id = file_buffer[deleting_name];
        var response = await fetch(`/submit_upload?recall=${deleting_id}`, {
            headers: {
                Authorization: `Basic ${NICK} ${TOKEN}`,
            },
        });
        if (response.ok) {
            document.getElementById(deleting_id).remove();
            delete file_buffer[deleting_name];
            window.alert(`${deleting_name} deleted!`);
        }
    }
}

document.addEventListener("keydown", (event) => {
    const keyName = event.key;
    if (event.ctrlKey) {
        if (keyName === "Enter") {
            msg_send();
        }
    }
});
