const auth = { Authorization: `Basic ${NICK} ${TOKEN}` };

async function new_chan() {
    var name = window.prompt("New channel's name");
    var head = auth;
    head["Content-Type"] = "application/json";
    var resp = await fetch("/channel", {
        method: "POST",
        headers: head,
        body: JSON.stringify({ name: name }),
    });
    if (resp.ok) {
        alert("Channel Created!");
        socket.emit("updating_channel");
    }
}

async function del_chan() {
    var id = Number(window.prompt("Channel ID", ""));
    if (id === undefined) {
        return;
    }
    if (!window.confirm(`Is channel ${id} going to be deleted?`)) {
        return;
    }
    var resp = await fetch(`/channel?id=${id}`, {
        method: "DELETE",
        headers: auth,
    });
    if (resp.ok) {
        alert("Channel Deleted!");
        socket.emit("updating_channel");
    }
}

async function sw_chan() {
    var id = Number(window.prompt("Channel's id"));
    var resp = await fetch(`/channel?sw_priv=${id}`, {
        method: "UPDATE",
        headers: auth,
    });
    if (resp.ok) {
        alert("Channel Updated!");
        socket.emit("updating_channel");
    }
}

async function re_chan() {
    var id = Number(window.prompt("Channel's id"));
    var new_name = window.prompt("Channel's name");
    var resp = await fetch(`/channel?id=${id}&name=${new_name}`, {
        method: "UPDATE",
        headers: auth,
    });
    if (resp.ok) {
        alert("Channel Updated!");
        socket.emit("updating_channel");
    }
}

async function del_user() {
    var name = window.prompt("User's name", "");
    if (name === "") {
        return;
    }
    if (!window.confirm(`Is user ${name} going to be deleted?`)) {
        return;
    }
    var resp = await fetch(`/online/${name}`, {
        method: "DELETE",
        headers: auth,
    });
    if (resp.ok) {
        alert("User kicked.")
    }
}

async function del_res() {
    var id = window.prompt("Resources's id", "");
    if (id == "") {
        return;
    }
    if (!window.confirm(`Is resource ${id} going to be deleted?`)) {
        return;
    }
    var resp = await fetch(`/resource/${id}`, {
        method: "DELETE",
        headers: auth,
    });
    if (resp.ok) {
        alert("Resource deleted.")
    }
}

async function del_msg() {
    var id = Number(window.prompt("Message's id", ""));
    if (id == 0) {
        return;
    }
    if (!window.confirm(`Is message ${id} going to be deleted?`)) {
        return;
    }
    var resp = await fetch(`/message/${id}`, {
        method: "DELETE",
        headers: auth,
    });
    if (resp.ok) {
        alert("Message Deleted.")
    }
}
