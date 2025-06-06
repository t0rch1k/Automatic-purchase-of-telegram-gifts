import asyncio
import time
from pyrogram import Client
from pyrogram.raw.functions.payments import (
    GetStarGifts,
    GetPaymentForm,
    SendPaymentForm,
    GetStarsStatus
)
from pyrogram.raw.types.payments import StarGiftsNotModified
from pyrogram.raw.types import (
    InputInvoiceStarGift,
    InputUserSelf,
    InputPeerSelf
)
from pyrogram.errors import FloodWait, UserDeactivated, AuthKeyUnregistered

API_ID = 1234
API_HASH = ""
SESSION_NAME = "test"

CHECK_INTERVAL_SECONDS = 300

known_gift_ids = set()
last_gift_list_hash = 0

app = Client(SESSION_NAME, api_id=API_ID, api_hash=API_HASH)


async def get_current_star_balance():
    try:
        status = await app.invoke(GetStarsStatus(peer=InputPeerSelf()))
        return status.balance.amount
    except Exception as e:
        print(f"Ошибка при получении баланса звезд: {e}")
        return 0


async def purchase_gift(gift_to_purchase):
    gift_id = gift_to_purchase.id
    gift_stars_cost = gift_to_purchase.stars

    print(f"Попытка покупки подарка ID: {gift_id} за {gift_stars_cost} звезд.")

    current_balance = await get_current_star_balance()
    if current_balance < gift_stars_cost:
        print(f"Недостаточно звезд для покупки. Баланс: {current_balance}, Нужно: {gift_stars_cost}")
        return False

    try:
        invoice_details = InputInvoiceStarGift(
            user_id=InputUserSelf(),
            gift_id=gift_id
        )
        payment_form_response = await app.invoke(
            GetPaymentForm(invoice=invoice_details)
        )
        print(f"Получена форма оплаты: ID={payment_form_response.form_id}")

        payment_result = await app.invoke(
            SendPaymentForm(
                form_id=payment_form_response.form_id,
                invoice=payment_form_response.invoice,
                credentials=None
            )
        )

        if hasattr(payment_result, 'CONSTRUCTOR_ID') and payment_result.CONSTRUCTOR_ID == 0xd00f764e:
            print(f"Покупка требует верификации через URL: {payment_result.url}. Автоматизация не удалась.")
            return False

        print(f"Подарок ID {gift_id} успешно куплен! Результат: {type(payment_result)}")
        return True

    except FloodWait as e:
        print(f"FloodWait во время покупки подарка ID {gift_id}: ждем {e.value} секунд.")
        await asyncio.sleep(e.value + 5)
        return False
    except Exception as e:
        print(f"Ошибка во время покупки подарка ID {gift_id}: {type(e).__name__} - {e}")
        return False


async def monitor_and_buy_new_gifts():
    global known_gift_ids
    global last_gift_list_hash

    print("Запуск мониторинга и покупки подарков...")

    try:
        initial_gifts_response = await app.invoke(GetStarGifts(hash=0))
        if hasattr(initial_gifts_response, 'gifts'):
            for gift in initial_gifts_response.gifts:
                known_gift_ids.add(gift.id)
            last_gift_list_hash = initial_gifts_response.hash
            print(f"Инициализация: {len(known_gift_ids)} подарков известно. Хэш: {last_gift_list_hash}")
        else:
            print(f"Инициализация: получен неожиданный ответ {type(initial_gifts_response)}")
    except Exception as e:
        print(f"Критическая ошибка при инициализации списка подарков: {e}. Завершение.")
        return

    while True:
        print(f"\nПроверка новых подарков... (Хэш для запроса: {last_gift_list_hash})")

        balance = await get_current_star_balance()
        print(f"Текущий баланс: {balance} ★")

        new_gifts_this_cycle = []
        try:
            star_gifts_response = await app.invoke(
                GetStarGifts(hash=last_gift_list_hash)
            )

            if hasattr(star_gifts_response, 'gifts'):
                print("Обнаружены изменения в списке подарков.")
                for gift_data in star_gifts_response.gifts:
                    if gift_data.id not in known_gift_ids:
                        if not gift_data.sold_out:
                            print(
                                f"Найден НОВЫЙ доступный подарок! ID: {gift_data.id}, Имя (если есть): {getattr(gift_data, 'title', 'N/A')}, Звезды: {gift_data.stars}")
                            new_gifts_this_cycle.append(gift_data)
                        else:
                            print(f"Найден новый, но уже распроданный подарок. ID: {gift_data.id}")
                        known_gift_ids.add(gift_data.id)

                last_gift_list_hash = star_gifts_response.hash
                print(f"Список подарков на сервере обновлен. Новый хэш: {last_gift_list_hash}")

                for new_gift in new_gifts_this_cycle:
                    print(f"Принято решение о покупке нового подарка ID: {new_gift.id}")
                    await purchase_gift(new_gift)
                    await asyncio.sleep(10)

            elif isinstance(star_gifts_response, StarGiftsNotModified):
                print("Список подарков не изменился.")
            else:
                print(f"Неожиданный ответ от GetStarGifts: {type(star_gifts_response)}")

        except FloodWait as e:
            print(f"FloodWait в цикле мониторинга: ждем {e.value} секунд.")
            await asyncio.sleep(e.value + 5)
        except (UserDeactivated, AuthKeyUnregistered) as e:
            print(f"Проблема с аккаунтом ({type(e).__name__}): {e}. Завершение работы.")
            break
        except Exception as e:
            print(f"Ошибка в цикле мониторинга: {type(e).__name__} - {e}")

        print(f"Следующая проверка через {CHECK_INTERVAL_SECONDS} секунд.")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


async def main():
    await app.start()
    try:
        await monitor_and_buy_new_gifts()
    finally:
        await app.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Мониторинг остановлен пользователем.")
    except Exception as e:
        print(f"Непредвиденная ошибка на верхнем уровне: {e}")
    finally:
        print("Завершение работы скрипта.")