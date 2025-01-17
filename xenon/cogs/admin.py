from discord.ext import commands as cmd
import discord
import traceback
import inspect
from contextlib import redirect_stdout
import textwrap
import io
from prettytable import PrettyTable
import asyncio

from utils import checks, formatter, extended


class Admin(cmd.Cog, command_attrs=dict(hidden=True)):
    def __init__(self, bot):
        self.bot = bot
        self._last_result = None

    @cmd.command()
    @checks.has_role_on_support_guild("Staff")
    @checks.has_role_on_support_guild("Staff")
    async def su(self, ctx, member: discord.Member, *, msg):
        """
        Execute a command in place of another user


        __Arguments__

        **member**: The user (must be a member of this guild)
        **msg**: The message. Doesn't need to be command
        """
        if member.id == ctx.bot.owner_id:
            raise cmd.CommandError("How about ... **no**?")

        webhook = await ctx.channel.create_webhook(name="sudo")
        await webhook.send(content=msg, username=member.name, avatar_url=member.avatar_url)
        await webhook.delete()

        await asyncio.sleep(1)  # Webhooks are slow

        message = ctx.message
        message.author = member
        message.content = msg
        await self.bot.process_commands(message)

    @cmd.command()
    @cmd.is_owner()
    async def sudo(self, ctx, *, command):
        """
        Execute a command and bypasses cooldown


        __Arguments__

        **command**: The command
        """
        message = ctx.message
        message.content = command

        new_ctx = await self.bot.get_context(message, cls=extended.Context)
        new_ctx.command.reset_cooldown(new_ctx)
        if isinstance(new_ctx.command, cmd.Group):
            for command in new_ctx.command.all_commands.values():
                command.reset_cooldown(new_ctx)

        await self.bot.invoke(new_ctx)

    @cmd.command(aliases=["rl"])
    @cmd.is_owner()
    async def reload(self, ctx, cog):
        """
        Reload a cog


        __Arguments__

        **cog**: The name of the cod
        """
        if cog.lower() == "all":
            failed = 0
            success = 0
            for cog in self.bot.config.extensions:
                try:
                    self.bot.reload_extension(cog)
                    success += 1
                except:
                    failed += 1
                    traceback.print_exc()

            await ctx.send(**ctx.em(f"Reloaded all cogs.\n**Success**: {success} **Failed**: {failed}", type="info"))
            return

        base_path = "cogs."
        try:
            self.bot.reload_extension(base_path + cog.lower())
            await ctx.send(**ctx.em(f"Successfully reloaded the cog named **{cog}**.", type="success"))
        except:
            traceback.print_exc()
            raise cmd.CommandError(f"Error while reloading the cog named **{cog}**.")

    @cmd.command()
    @checks.has_role_on_support_guild("Admin")
    async def restart(self, ctx):
        await ctx.send(**ctx.em("Reastarting ...", type="info"))
        await self.bot.close()

    @cmd.command(name="exec")
    @cmd.is_owner()
    async def _exec(self, ctx, *, body: str):
        """
        Executes something, uses exec not eval -> returns None


        __Arguments__

        **body**: The code to get executed
        """

        def cleanup_code(content):
            """Automatically removes code blocks from the code."""
            # remove ```py\n```
            if content.startswith('```') and content.endswith('```'):
                return '\n'.join(content.split('\n')[1:-1])

            # remove `foo`
            return content.strip('` \n')

        env = {
            'bot': self.bot,
            'ctx': ctx,
            'channel': ctx.channel,
            'author': ctx.author,
            'guild': ctx.guild,
            'msg': ctx.message,
            '_': self._last_result
        }

        env.update(globals())

        body = cleanup_code(body)
        stdout = io.StringIO()

        to_compile = f'async def func():\n{textwrap.indent(body, "  ")}'

        try:
            exec(to_compile, env)
        except Exception as e:
            return await ctx.send(f'```py\n{e.__class__.__name__}: {e}\n```')

        func = env['func']
        try:
            with redirect_stdout(stdout):
                ret = await func()

        except:
            value = stdout.getvalue()
            await ctx.send(f'```py\n{value}{traceback.format_exc()}\n```')
        else:
            value = stdout.getvalue()
            try:
                await ctx.message.add_reaction('\u2705')
            except:
                pass

            if ret is None:
                if value:
                    await ctx.send(f'```py\n{value}\n```')
            else:
                self._last_result = ret
                await ctx.send(f'```py\n{value}{ret}\n```')

    @cmd.command()
    @cmd.is_owner()
    async def eval(self, ctx, *, expression: str):
        """
        Evaluate a single expression and return the result


        __Arguments__

        **expressions**: The expression
        """
        to_eval = expression.replace("await ", "")
        try:
            result = eval(to_eval)
            if inspect.isawaitable(result):
                result = await result
        except Exception as e:
            result = type(e).__name__ + ": " + str(e)

        result = str(result).replace(ctx.config.token, "you tried")

        embed = ctx.em("")["embed"]
        embed.title = "Eval Result"
        embed.add_field(name="Input 📥", value=f"```Python\n{expression}```", inline=False)
        embed.add_field(name="Output 📤", value=f"```Python\n{result}```", inline=False)

        await ctx.send(embed=embed)

    @cmd.command()
    @cmd.is_owner()
    async def query(self, ctx, timeout: float = 0.5, *, expression: str):
        """
        Evaluate a single expression on all shards and return the results


        __Arguments__

        **expressions**: The expression
        """
        results = await self.bot.query(expression, timeout=timeout)
        table = PrettyTable()
        table.field_names = ["Shard-Id", "Result"]
        for shards, result in sorted(results, key=lambda r: sum(r[0])):
            table.add_row([", ".join([str(s) for s in shards]), result])

        pages = formatter.paginate(str(table))
        for page in pages:
            await ctx.send(f"```diff\n{page}```")


def setup(bot):
    bot.add_cog(Admin(bot))
