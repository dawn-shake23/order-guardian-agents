from typing import Optional, Any, List, Dict

class MySQLMemoryRepo:
    def __init__(self):
        # 实际项目中这里应该初始化真实的MySQL连接
        self.data = {}
    
    def get(self, table: str, id: str) -> Optional[Dict[str, Any]]:
        """
        从表中获取数据
        """
        table_data = self.data.get(table, {})
        return table_data.get(id)
    
    def save(self, table: str, id: str, data: Dict[str, Any]) -> bool:
        """
        保存数据到表中
        """
        if table not in self.data:
            self.data[table] = {}
        self.data[table][id] = data
        return True
    
    def delete(self, table: str, id: str) -> bool:
        """
        从表中删除数据
        """
        if table in self.data and id in self.data[table]:
            del self.data[table][id]
            return True
        return False
    
    def query(self, table: str, conditions: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        根据条件查询数据
        """
        result = []
        if table in self.data:
            for item in self.data[table].values():
                match = True
                for key, value in conditions.items():
                    if item.get(key) != value:
                        match = False
                        break
                if match:
                    result.append(item)
        return result