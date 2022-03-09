import abc
import os
import re
import time
from abc import abstractmethod
from decimal import Decimal
from typing import Dict

import requests

DEBUG = bool(os.environ.get("DEBUG", False))
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHANNEL = os.environ.get("TELEGRAM_CHANNEL", 0)

FUEL_PRICE_KEYS = ('Petrol95', 'Petrol98', 'Diesel', 'DieselPremium')


def empty_prices() -> Dict[str, Decimal]:
    return {key: Decimal(0) for key in FUEL_PRICE_KEYS}


class Provider(abc.ABC):
    url: str
    prices: Dict[str, Decimal]
    _name: str

    def __init__(self):
        self.prices = empty_prices()

    def _get_html(self) -> str:
        filename = f"{self._name}.html"
        if __debug__ and not os.path.isfile(filename):
            response = requests.get(self.url)
            html = response.text
            with open(filename, "w") as f:
                f.write(html)
        else:
            with open(filename, "r") as f:
                html = f.read()
        return html

    @abstractmethod
    def get_prices(self) -> Dict[str, Decimal]:
        raise NotImplementedError

    def report_price_change(self, price_diff: Dict[str, Decimal]):
        message = ", ".join(
            f"{kind}: {change:+5.3f}€/L ({self.prices[kind]:5.3} €/L)" for kind, change in price_diff.items()
        )
        print(self._name, message)
        message = f"[{self._name}] Price update: {message}"
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json=dict(chat_id=TELEGRAM_CHANNEL, text=message, parse_mode="Markdown"),
        )

    def check_and_report_change(self, new_prices: Dict[str, Decimal]):
        price_diff = empty_prices()
        for kind in FUEL_PRICE_KEYS:
            if not self.prices[kind] == new_prices[kind]:
                price_diff[kind] = new_prices[kind] - self.prices[kind]
                self.prices[kind] = new_prices[kind]
        if any(price_diff.values()):
            self.report_price_change(price_diff)


class Neste(Provider):
    _name = "Neste"
    url = "https://www.neste.lv/lv/content/degvielas-cenas"

    def get_prices(self) -> Dict[str, Decimal]:
        html = self._get_html()
        fuel_price_table = re.search(r"(<table.*</table>)", html, re.S)
        if not fuel_price_table:
            raise
        fuel_prices = empty_prices()
        for row in re.findall("(<tr.*?</tr>)", fuel_price_table.group(1), re.S)[1:5]:
            cols = re.findall("<p>(.*?)</p>", row, re.S)
            price = re.search(r"<(strong|b)>([\d.,]*)</(strong|b)>", cols[1]).group(2)
            if "95" in cols[0]:
                fuel_prices['Petrol95'] = Decimal(price)
            elif "Neste Futura 98" in cols[0]:
                fuel_prices['Petrol98'] = Decimal(price)
            elif "Neste Futura D" in cols[0]:
                fuel_prices['Diesel'] = Decimal(price)
            elif "Neste Pro Diesel" in cols[0]:
                fuel_prices['DieselPremium'] = Decimal(price)
            else:
                raise ValueError(row)
        return fuel_prices


class Virsi(Provider):
    _name = "Virši"
    url = "https://www.virsi.lv/lv/degvielas-cena"

    def get_prices(self) -> Dict[str, Decimal]:
        html = self._get_html()

        diesel_price = re.search(r"price-item type-dd.*?<p class=\"price\">([\d.,]*)</p>", html, re.S).group(1)
        petrol_price = re.search(r"price-item type-95e.*?<p class=\"price\">([\d.,]*)</p>", html, re.S).group(1)
        petrol_premium_price = re.search(r"price-item type-98e.*?<p class=\"price\">([\d.,]*)</p>", html, re.S).group(1)

        fuel_prices = dict(
            Petrol95=Decimal(petrol_price),
            Petrol98=Decimal(petrol_premium_price),
            Diesel=Decimal(diesel_price),
            DieselPremium=Decimal(0)
        )
        return fuel_prices


class Viada(Provider):
    _name = "Viada"
    url = "https://www.viada.lv/zemakas-degvielas-cenas/"

    def get_prices(self) -> Dict[str, Decimal]:
        html = self._get_html()
        fuel_price_table = re.search(r"<tbody>(.*?)</tbody>", html, re.S)
        if not fuel_price_table:
            raise
        fuel_prices = empty_prices()
        for row in re.findall("<tr>(.*?)</tr>", fuel_price_table.group(1), re.S)[1:]:
            cols = re.findall("<td>(.*?)</td>", row, re.S)
            price = re.search(r"([\d.]+) EUR", cols[1]).group(1)
            if "petrol_95ectoplus_new" in cols[0]:
                fuel_prices['Petrol95'] = Decimal(price)
            elif "petrol_98_new" in cols[0]:
                fuel_prices['Petrol98'] = Decimal(price)
            elif "petrol_d_new" in cols[0]:
                fuel_prices['Diesel'] = Decimal(price)
            elif "petrol_d_ecto_new" in cols[0]:
                fuel_prices['DieselPremium'] = Decimal(price)
        return fuel_prices


if __name__ == '__main__':
    providers = [Neste(), Virsi(), Viada()]

    for provider in providers:
        provider.prices = provider.get_prices()
        provider.report_price_change(empty_prices())

    while True:
        for provider in providers:
            provider.check_and_report_change(provider.get_prices())
        time.sleep(600)
