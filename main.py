# main.py
import discord
from discord.ext import commands
import asyncio
import os
from dotenv import load_dotenv
from keep_alive import keep_alive
from utils.utils import charger_config

# ───────────── Création du dossier /data si nécessaire ─────────────
os.makedirs("/data", exist_ok=True)

# ───────────── Lancement du serveur keep-alive ─────────────
keep_alive()

# ───────────── Chargement des variables d’environnement ─────────────
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# ───────────── Création du bot avec intents ─────────────
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ───────────── Gestion globale des erreurs ─────────────
@bot.event
async def on_error(event, *args, **kwargs):
    try:
        import traceback
        error_info = traceback.format_exc()
        print(f"[ERREUR GLOBALE] {error_info}")
        config = charger_config()
        log_channel_id = int(config.get("log_erreurs_channel", 0))
        if not log_channel_id:
            return
        for guild in bot.guilds:
            channel = guild.get_channel(log_channel_id)
            if channel:
                embed = discord.Embed(
                    title="❌ Erreur globale détectée",
                    description=f"```{error_info[:4000]}```",
                    color=discord.Color.red()
                )
                await channel.send(embed=embed)
    except Exception as e:
        print(f"[ERREUR dans on_error] {e}")

# ───────────── Bot prêt ─────────────
@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user} (ID : {bot.user.id})")
    try:
        print("🔄 Synchronisation des commandes slash...")
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)} commandes synchronisées avec succès.")
    except Exception as e:
        print(f"❌ Erreur lors de la synchronisation des commandes : {e}")

# ───────────── Chargement des Cogs ─────────────
async def load_cogs():
    try:
        print("🔧 Chargement des Cogs en cours...")
        from commands.admin import setup_admin_commands
        from commands.utilisateur import setup_user_commands
        from commands.support import setup_support_commands
        from commands.events import setup as setup_events
        from commands import whitelist
        from commands import loisir
        from commands import missions
        from commands import reaction_roles
        from commands import checkin

        await setup_admin_commands(bot)
        print("✅ AdminCommands chargé")

        await setup_user_commands(bot)
        print("✅ UtilisateurCommands chargé")

        await setup_support_commands(bot)
        print("✅ SupportCommands chargé")

        await setup_events(bot)
        print("✅ Events chargé")

        await whitelist.setup(bot)
        print("✅ Whitelist chargé")

        await loisir.setup(bot)
        print("✅ LoisirCommands chargé")

        await missions.setup(bot)
        print("✅ Missions chargé")

        await reaction_roles.setup(bot)
        print("✅ ReactionRole chargé")

        await checkin.setup(bot)
        print("✅ Checkin chargé")
    except Exception as e:
        print(f"❌ Erreur lors du chargement des Cogs : {e}")
        import traceback
        traceback.print_exc()


# ───────────── Lancement du bot ─────────────
if __name__ == "__main__":
    async def main():
        await load_cogs()
        await bot.start(TOKEN)

    asyncio.run(main())
