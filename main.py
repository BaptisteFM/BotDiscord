import discord
from discord.ext import commands
import asyncio
import os
from dotenv import load_dotenv
from keep_alive import keep_alive
from utils.utils import charger_config

# ───────────── Lancement du serveur HTTP keep-alive ─────────────
keep_alive()

# ───────────── Chargement des variables d'environnement ─────────────
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# ───────────── Création du bot avec les intents ─────────────
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ───────────── Log d’erreur global dans un salon Discord ─────────────
@bot.event
async def on_error(event, *args, **kwargs):
    try:
        import traceback
        error_info = traceback.format_exc()
        print(f"[ERREUR GLOBALE] {error_info}")  # ✅ Debug Render/local

        config = charger_config()
        log_channel_id = int(config.get("log_erreurs_channel", 0))
        if not log_channel_id:
            return

        for guild in bot.guilds:
            channel = guild.get_channel(log_channel_id)
            if channel:
                embed = discord.Embed(
                    title="⚠️ Erreur globale",
                    description=f"```{error_info[:4000]}```",  # Discord limite à 4096 caractères
                    color=discord.Color.red()
                )
                await channel.send(embed=embed)
    except Exception as e:
        print(f"[ERREUR dans on_error] {e}")

# ───────────── Quand le bot est prêt ─────────────
@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user} (ID : {bot.user.id})")
    try:
        initial_commands = bot.tree.get_commands()
        print("DEBUG - Commandes détectées avant sync:", initial_commands)

        synced = await bot.tree.sync()
        print(f"✅ {len(synced)} commandes slash synchronisées globalement.")

        updated_commands = bot.tree.get_commands()
        print("DEBUG - Commandes après sync:", updated_commands)
    except Exception as e:
        print(f"❌ Erreur lors de la synchronisation des commandes : {e}")

# ───────────── Chargement des Cogs (commandes) ─────────────
async def load_cogs():
    try:
        print("DEBUG - Début du chargement des cogs")
        from commands.admin import setup_admin_commands
        from commands.utilisateur import setup_user_commands
        from commands.support import setup_support_commands
        from commands.test_command import setup as setup_test
        from commands.events import setup as setup_events
        from commands import whitelist
        await setup_test(bot)
        await setup_admin_commands(bot)
        print("✅ AdminCommands chargé")
        await setup_user_commands(bot)
        print("✅ UtilisateurCommands chargé")
        await setup_support_commands(bot)
        print("✅ SupportCommands chargé")
        await setup_events(bot)
        await whitelist.setup(bot)
        
    except Exception as e:
        print(f"❌ Erreur lors du chargement des Cogs : {e}")


# ───────────── Lancement principal ─────────────
if __name__ == "__main__":
    async def main():
        await load_cogs()
        await bot.start(TOKEN)

    asyncio.run(main())