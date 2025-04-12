import discord
from discord.ext import commands
import asyncio
import os
from dotenv import load_dotenv
from keep_alive import keep_alive
from utils.utils import charger_config

# ───────────── Lancement keep-alive ─────────────
keep_alive()

# ───────────── Chargement des variables d'environnement ─────────────
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# ───────────── Création du bot ─────────────
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ───────────── Log d'erreur global dans un salon ─────────────
@bot.event
async def on_error(event, *args, **kwargs):
    try:
        config = charger_config()
        log_channel_id = int(config.get("log_erreurs_channel", 0))
        if log_channel_id:
            for guild in bot.guilds:
                channel = guild.get_channel(log_channel_id)
                if channel:
                    import traceback
                    error_info = traceback.format_exc()
                    embed = discord.Embed(title="⚠️ Erreur détectée", description=f"```{error_info[:4000]}```", color=discord.Color.red())
                    await channel.send(embed=embed)
    except Exception as e:
        print(f"Erreur lors de l'envoi du log : {e}")

# ───────────── Événement on_ready ─────────────
@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user} (ID : {bot.user.id})")
    try:
        initial_commands = bot.tree.get_commands()
        print("DEBUG - Commandes détectées avant sync:", initial_commands)

        synced = await bot.tree.sync()
        print(f"✅ {len(synced)} commandes slash synchronisées globalement après réinitialisation.")

        updated_commands = bot.tree.get_commands()
        print("DEBUG - Commandes après sync:", updated_commands)
    except Exception as e:
        print(f"❌ Erreur de synchronisation des commandes slash : {e}")

# ───────────── Chargement des cogs ─────────────
async def load_cogs():
    print("DEBUG - Début du chargement des cogs")
    from commands.admin import setup_admin_commands
    from commands.utilisateur import setup_user_commands
    from commands.support import setup_support_commands

    await setup_admin_commands(bot)
    print("DEBUG - AdminCommands chargé")
    await setup_user_commands(bot)
    print("DEBUG - UtilisateurCommands chargé")
    await setup_support_commands(bot)
    print("DEBUG - SupportCommands chargé")
    print("✅ Cogs chargés avec succès.")

# ───────────── Lancement du bot ─────────────
if __name__ == "__main__":
    async def main():
        await load_cogs()
        await bot.start(TOKEN)
    asyncio.run(main())
