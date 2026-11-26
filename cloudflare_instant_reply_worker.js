/**
 * БЕСПЛАТНЫЙ CLOUDFLARE WORKER ДЛЯ МГНОВЕННОЙ ПОДСТАНОВКИ ЦЕНЫ В ГРН (ОПЦИОНАЛЬНО)
 *
 * Как работает:
 * Когда GitHub Actions присылает тебе карточку товара в Telegram, ты отвечаешь (Reply)
 * на сообщение числом — например: "6000" или "5800 грн".
 * Этот воркер ловит твой ответ через Webhook за 0.1 секунды, отрезает нижний служебный блок
 * со ссылками и ценой в $, подставляет "💰 Ціна: 6000 грн" и сразу присылает тебе
 * чистый пост с фото, готовый для пересылки в твой канал или копирования в Instagram.
 *
 * Настройка (100% бесплатно, до 100 000 запросов в день):
 * 1. Зайди на https://dash.cloudflare.com/ -> Workers & Pages -> Create Worker.
 * 2. Вставь этот код и нажми Deploy.
 * 3. В настройках воркера (Settings -> Variables and Secrets) добавь переменную:
 *    TELEGRAM_BOT_TOKEN = твой токен от @BotFather
 * 4. Привяжи вебхук, открыв в браузере ссылку (подставь свой токен и URL воркера):
 *    https://api.telegram.org/bot<ТВОЙ_ТОКЕН>/setWebhook?url=https://<ТВОЙ_ВОРКЕР>.workers.dev
 *    (Если используешь этот воркер для мгновенных ответов, в deal_hunter.py можно закомментировать вызов process_telegram_price_replies).
 */

export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("US Deal Bot Instant Price Worker is running!", { status: 200 });
    }

    try {
      const update = await request.json();
      const msg = update.message || update.channel_post;
      if (!msg || !msg.reply_to_message || !msg.text) {
        return new Response("OK", { status: 200 });
      }

      const userText = msg.text.trim();
      const priceMatch = userText.match(/(\d[\d\s.,]*)/);
      if (!priceMatch) {
        return new Response("OK", { status: 200 });
      }

      const cleanPrice = priceMatch[1].replace(/[^\d]/g, "");
      if (!cleanPrice) {
        return new Response("OK", { status: 200 });
      }

      const replyTo = msg.reply_to_message;
      const originalText = replyTo.caption || replyTo.text || "";
      if (!originalText) {
        return new Response("OK", { status: 200 });
      }

      // Отрезаем нижний служебный блок байера (после линии ────────────)
      const postBody = originalText.split("────────────")[0].trim();

      // Подставляем цену в гривнах
      let updatedPost = postBody.replace(/💰\s*Ціна:.*/g, `💰 Ціна: ${cleanPrice} грн`);
      if (!updatedPost.includes(`💰 Ціна: ${cleanPrice} грн`)) {
        updatedPost += `\n\n💰 Ціна: ${cleanPrice} грн`;
      }

      const chatId = msg.chat.id;
      const token = env.TELEGRAM_BOT_TOKEN;

      if (replyTo.photo && replyTo.photo.length > 0) {
        const bestPhotoId = replyTo.photo[replyTo.photo.length - 1].file_id;
        await fetch(`https://api.telegram.org/bot${token}/sendPhoto`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            chat_id: chatId,
            photo: bestPhotoId,
            caption: updatedPost.slice(0, 1024),
            reply_to_message_id: msg.message_id,
          }),
        });
      } else {
        await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            chat_id: chatId,
            text: updatedPost.slice(0, 4096),
            reply_to_message_id: msg.message_id,
          }),
        });
      }

      return new Response("OK", { status: 200 });
    } catch (err) {
      return new Response("OK", { status: 200 });
    }
  },
};
