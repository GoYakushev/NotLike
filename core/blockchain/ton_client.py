from toncenter_client import TonCenterClient
from tonsdk.utils import Address, to_nano
from ton import TonClient
from tonsdk.contract.wallet import Wallets, WalletVersionEnum
from tonsdk.contract import JettonWallet
from tonsdk.boc import Cell  #  Cell

class TONClient:
    def __init__(self, api_key: str):
        self.client = TonCenterClient(api_key=api_key)
        self.ton_client = TonClient(testnet=False)

    def create_wallet(self) -> dict:
        """Создает новый кошелек TON (v4r2)."""
        mnemonics, wallet = Wallets.create(version=WalletVersionEnum.v4r2)
        return {
            'address': wallet.address.to_string(True, True, True),
            'private_key': ' '.join(mnemonics)
        }

    async def get_balance(self, address: str, token_address: str = None) -> float:
        """Возвращает баланс кошелька TON (в TON) или жетона (Jetton)."""
        try:
            if token_address is None:
                # Баланс TON
                account_info = await self.client.get_address_information(address=Address(address))
                balance = account_info.balance / (10 ** 9)  # NanoTON to TON
            else:
                # Баланс жетона (Jetton)
                jetton_wallet = JettonWallet(provider=self.ton_client, master_address=Address(token_address))
                owner_address = Address(address)
                wallet_address = await jetton_wallet.get_wallet_address(owner_address)
                jetton_wallet_contract = JettonWallet(provider=self.ton_client, address=wallet_address)
                balance_data = await jetton_wallet_contract.get_data()
                balance = int(balance_data['balance']) / (10 ** int(balance_data['jetton_master'].metadata['decimals']))

            return balance

        except Exception as e:
            print(f"Error getting TON balance: {e}")
            return 0.0

    async def transfer(self, sender_private_key: str, recipient_address: str, amount: float, token_address: str = None) -> dict:
        """Переводит TON или жетоны (Jettons)."""
        try:
            mnemonics = sender_private_key.split()
            sender_wallet = Wallets.from_mnemonics(mnemonics, version=WalletVersionEnum.v4r2)[1]
            seqno = await self.ton_client.get_seqno(sender_wallet.address)

            if token_address is None:
                # Перевод TON
                query = sender_wallet.create_transfer_message(
                    to_addr=recipient_address,
                    amount=to_nano(amount, "ton"),
                    seqno=seqno,
                )
            else:
                # Перевод Jetton
                jetton_wallet = JettonWallet(provider=self.ton_client, master_address=Address(token_address))
                sender_jetton_wallet_address = await jetton_wallet.get_wallet_address(sender_wallet.address)
                sender_jetton_wallet = JettonWallet(provider=self.ton_client, address=sender_jetton_wallet_address)

                token_info = await jetton_wallet.get_data()
                decimals = int(token_info['jetton_master'].metadata['decimals'])

                query = sender_jetton_wallet.create_transfer_message(
                    to_address=Address(recipient_address),
                    amount=to_nano(amount, decimals),  #  nano-jettons
                    seqno=seqno,
                    forward_ton_amount=to_nano(0.1, "ton"),  #  forward TON
                    response_address=sender_wallet.address
                )


            await self.ton_client.raw_send_message(query["message"].to_boc(False))
            return {'success': True, 'transaction_id': 'Not implemented'}

        except Exception as e:
            print(f"Error transferring TON: {e}")
            return {'success': False, 'error': str(e)} 