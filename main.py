# main.py
import discord
from discord.ext import commands
import asyncio
import os
import json
from dotenv import load_dotenv
from keep_alive import keep_alive
from utils.utils import charger_permissions, PERMISSIONS_PATH
from discord import app_commands

# ─── Préparation /data et JSON de permissions ───────────────────
os.makedirs("/data", exist_ok=True)
if not os.path.exists(PERMISSIONS_PATH):
    with open(PERMISSIONS_PATH, "w", encoding="utf-8") as f:
        json.dump({}, f, indent=4)

# ─── Keep-alive et chargement du token ──────────────────────────
keep_alive()
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# ─── Intents ────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # 1) Chargement de tous tes Cogs
        from commands.admin import setup_admin_commands
        from commands.utilisateur import setup_user_commands
        from commands.support import setup_support_commands
        from commands.test_command import setup as setup_test
        from commands.events import setup as setup_events
        from commands import whitelist, loisir, missions, reaction_roles, checkin

        await setup_test(self)
        await setup_admin_commands(self)
        await setup_user_commands(self)
        await setup_support_commands(self)
        await setup_events(self)
        await whitelist.setup(self)
        await loisir.setup(self)
        await missions.setup(self)
        await reaction_roles.setup(self)
        await checkin.setup(self)

    async def on_ready(self):
        print(f"✅ Connecté en tant que {self.user} (ID : {self.user.id})")

        # 2) Sync par-guilde pour que nos slash-commands soient disponibles
        for guild in self.guilds:
            try:
                synced = await self.tree.sync(guild=guild)
                print(f"🔄 {len(synced)} commandes synchronisées dans {guild.name}")
            except Exception as e:
                print(f"❌ Erreur de sync pour {guild.name} : {e}")

        # 3) Appliquer notre whitelist de commandes
        await self.apply_command_permissions()

    async def apply_command_permissions(self):
        """
        Pour chaque guild et chaque commande slash :
          1) cmd.edit(...) pour masquer la commande à tout le monde
          2) Charger permissions.json
          3) Construire la liste AppCommandPermission pour les rôles/users autorisés
          4) tree.set_permissions(...) avec cette liste (vide = invisible)
        """
        permissions_config = charger_permissions()  # ex: {"checkin": ["123"], "support": ["456"]}

        for guild in self.guilds:
            for cmd in self.tree.get_commands(guild=guild):
                # 1) Masquer pour tout le monde
                await cmd.edit(
                    guild=guild,
                    default_member_permissions=0,  # AUCUN droit → caché
                    dm_permission=False
                )

                # 2) Lookup dans le JSON
                allowed = permissions_config.get(cmd.name)
                if allowed is None:
                    # fallback sur la catégorie si tu as fait cmd.category = "support" par ex.
                    cat = getattr(cmd, "category", None)
                    allowed = permissions_config.get(cat, [])

                # 3) Construire les AppCommandPermission
                perms: list[app_commands.AppCommandPermission] = []
                for id_str in allowed:
                    id_int = int(id_str)
                    if guild.get_role(id_int) is not None:
                        perms.append(app_commands.AppCommandPermission(
                            id=id_int,
                            type=app_commands.AppCommandPermissionType.role,
                            permission=True
                        ))
                    else:
                        perms.append(app_commands.AppCommandPermission(
                            id=id_int,
                            type=app_commands.AppCommandPermissionType.user,
                            permission=True
                        ))

                # 4) Appliquer : liste vide = invisible pour tous
                await self.tree.set_permissions(cmd, guild=guild, permissions=perms)

# ─── Démarrage du bot ───────────────────────────────────────────
bot = MyBot()

if __name__ == "__main__":
    asyncio.run(bot.start(TOKEN))
